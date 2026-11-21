#!/usr/bin/env python3
"""Publish the S3 data sources to Tableau Cloud or Server with tableauserverclient (SPEC § 3.1 S3, E5).

For each data source in model.DATASOURCES:
  1. bind the Databricks connection of the committed .tds to the target environment (host, HTTP path);
  2. publish the live variant (Overwrite) with the Databricks token embedded as the connection credential;
  3. publish the extract variant under "<name> (Extract)", create its extract server-side, download it as .tdsx,
     write the refresh settings into its <extract> (incremental key for NYC trips, a rolling 24-month extract filter
     anchored at --retention-anchor) and republish the .tdsx;
  4. grant the row-level security groups View, Connect and API Access (VizQL Data Service) on both variants.

Environment: TABLEAU_SERVER, TABLEAU_SITE, TABLEAU_PAT_NAME, TABLEAU_PAT_SECRET, TABLEAU_PROJECT,
DATABRICKS_SERVER_HOSTNAME, DATABRICKS_HTTP_PATH, DATABRICKS_TOKEN.

    python3 jobs/publish.py [--live-only] [--dry-run]
"""

from __future__ import annotations

import argparse
import io
import os
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from model import DATASOURCES, PICKUP_GROUP, TERRITORY_GROUP, DataSource  # noqa: E402

USER_NS = "http://www.tableausoftware.com/xml/user"
ET.register_namespace("user", USER_NS)
GROUPS = {"slc_wwi_sales_orders": [TERRITORY_GROUP], "slc_wwi_stock": [TERRITORY_GROUP], "slc_nyc_trips": [PICKUP_GROUP]}
RETENTION_MONTHS = 24


def _parse(text: str) -> ET.Element:
    return ET.fromstring(text.encode("utf-8"))


def _serialize(root: ET.Element) -> str:
    return "<?xml version='1.0' encoding='utf-8' ?>\n" + ET.tostring(root, encoding="unicode") + "\n"


def bind_connection(tds_text: str, host: str, http_path: str) -> str:
    """Set the Databricks host and SQL warehouse HTTP path on every databricks named connection."""
    if not host or not http_path:
        raise ValueError("DATABRICKS_SERVER_HOSTNAME and DATABRICKS_HTTP_PATH are required")
    root = _parse(tds_text)
    conns = root.findall("connection/named-connections/named-connection/connection[@class='databricks']")
    if not conns:
        raise ValueError("no databricks named connection in the data source")
    for c in conns:
        c.set("server", host)
        c.set("v-http-path", http_path)
    return _serialize(root)


def patch_extract(tds_text: str, ds: DataSource, retention_anchor: str) -> str:
    """Write the extract refresh settings into an extract-enabled data source document."""
    root = _parse(tds_text)
    extract = root.find("extract")
    if extract is None or extract.find("connection") is None:
        raise ValueError(f"{ds.name}: the document has no extract connection to configure")
    conn = extract.find("connection")
    for old in conn.findall("refresh"):
        conn.remove(old)
    if ds.incremental_key:
        ET.SubElement(conn, "refresh", {"increment-key": f"[{ds.incremental_key}]", "incremental-updates": "true"})
    for old in extract.findall("filter"):
        extract.remove(old)
    if ds.incremental_key:
        date_col = "trip_pickup_date"
        ET.SubElement(extract, "filter", {
            "class": "relative-date", "column": f"[{date_col}]", "first-period": str(1 - RETENTION_MONTHS),
            "last-period": "0", "period-type-v2": "month", "period-anchor": f"#{retention_anchor}#",
            "include-future": "false", "include-null": "false", "logical-table-scoped": "true"})
    return _serialize(root)


def _tds_in_tdsx(data: bytes) -> tuple[str, dict[str, bytes]]:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        files = {n: z.read(n) for n in z.namelist()}
    tds_names = [n for n in files if n.endswith(".tds")]
    if len(tds_names) != 1:
        raise ValueError(f"expected one .tds inside the .tdsx, found {tds_names}")
    return tds_names[0], files


def _repack(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, content in files.items():
            z.writestr(name, content)
    return buf.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live-only", action="store_true")
    parser.add_argument("--retention-anchor", default="2024-12-31", help="anchor of the rolling 24-month extract filter")
    parser.add_argument("--dry-run", action="store_true", help="bind and print the plan without contacting Tableau")
    args = parser.parse_args()

    host, http_path = os.environ.get("DATABRICKS_SERVER_HOSTNAME", ""), os.environ.get("DATABRICKS_HTTP_PATH", "")
    bound = {ds.key: bind_connection((HERE / "datasources" / ds.file).read_text(), host, http_path) for ds in DATASOURCES}
    if args.dry_run:
        for ds in DATASOURCES:
            print(f"publish {ds.name!r}" + ("" if args.live_only else f" and {ds.extract_name!r}")
                  + f" -> groups {GROUPS[ds.key]}")
        return

    import tableauserverclient as TSC

    server = TSC.Server(os.environ["TABLEAU_SERVER"], use_server_version=True)
    server.auth.sign_in(TSC.PersonalAccessTokenAuth(os.environ["TABLEAU_PAT_NAME"], os.environ["TABLEAU_PAT_SECRET"],
                                                    site_id=os.environ.get("TABLEAU_SITE", "")))
    try:
        projects = [p for p in TSC.Pager(server.projects) if p.name == os.environ["TABLEAU_PROJECT"]]
        if len(projects) != 1:
            raise LookupError(f"project {os.environ['TABLEAU_PROJECT']!r} not found exactly once")
        project_id = projects[0].id
        creds = TSC.ConnectionCredentials("token", os.environ["DATABRICKS_TOKEN"], embed=True)
        groups = {g.name: g for g in TSC.Pager(server.groups)}
        overwrite = TSC.Server.PublishMode.Overwrite
        with tempfile.TemporaryDirectory() as tmp:
            for ds in DATASOURCES:
                variants = [ds.name] if args.live_only else [ds.name, ds.extract_name]
                for name in variants:
                    path = Path(tmp) / f"{ds.key}.tds"
                    path.write_text(bound[ds.key])
                    item = server.datasources.publish(TSC.DatasourceItem(project_id, name), str(path), overwrite,
                                                      connection_credentials=creds)
                    print(f"published {name} ({item.id})", flush=True)
                    if name == ds.extract_name:
                        server.jobs.wait_for_job(server.datasources.create_extract(item))
                        tdsx = Path(server.datasources.download(item.id, filepath=tmp, include_extract=True))
                        tds_name, files = _tds_in_tdsx(tdsx.read_bytes())
                        files[tds_name] = patch_extract(files[tds_name].decode("utf-8"), ds,
                                                        args.retention_anchor).encode("utf-8")
                        packed = Path(tmp) / f"{ds.key}_extract.tdsx"
                        packed.write_bytes(_repack(files))
                        item = server.datasources.publish(TSC.DatasourceItem(project_id, name), str(packed), overwrite,
                                                          connection_credentials=creds)
                        print(f"configured extract refresh for {name}", flush=True)
                    rules = []
                    for gname in GROUPS[ds.key]:
                        if gname not in groups:
                            raise LookupError(f"Tableau group {gname!r} does not exist (prerequisite, guide § 4)")
                        rules.append(TSC.PermissionsRule(groups[gname], {
                            TSC.Permission.Capability.Read: TSC.Permission.Mode.Allow,
                            TSC.Permission.Capability.Connect: TSC.Permission.Mode.Allow,
                            TSC.Permission.Capability.VizqlDataApiAccess: TSC.Permission.Mode.Allow,
                        }))
                    server.datasources.update_permissions(item, rules)
    finally:
        server.auth.sign_out()


if __name__ == "__main__":
    main()
