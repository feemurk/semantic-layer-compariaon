#!/usr/bin/env python3
"""Extract refresh automation for the S3 extract variants (SPEC § 3.1 "Partition and refresh automation", E6).

  incremental  NYC trips: append rows whose pickup_ts exceeds the extract's highest value (the increment key written
               by publish.py). The WWI extracts have no increment key and refresh in full.
  rollover     Monthly: a full refresh of every extract. The rolling 24-month relative-date extract filter then drops
               the month that left the window, which an incremental refresh cannot do.

The live variants need no refresh. Environment as jobs/publish.py.

    python3 jobs/refresh.py incremental|rollover [--no-wait]
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from model import DATASOURCES  # noqa: E402


def plan(mode: str) -> list[tuple[str, bool]]:
    """(extract data source name, incremental) per refresh in this mode."""
    if mode == "incremental":
        return [(ds.extract_name, bool(ds.incremental_key)) for ds in DATASOURCES]
    if mode == "rollover":
        return [(ds.extract_name, False) for ds in DATASOURCES]
    raise ValueError(f"unknown mode {mode!r}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["incremental", "rollover"])
    parser.add_argument("--no-wait", action="store_true")
    args = parser.parse_args()

    import tableauserverclient as TSC

    server = TSC.Server(os.environ["TABLEAU_SERVER"], use_server_version=True)
    server.auth.sign_in(TSC.PersonalAccessTokenAuth(os.environ["TABLEAU_PAT_NAME"], os.environ["TABLEAU_PAT_SECRET"],
                                                    site_id=os.environ.get("TABLEAU_SITE", "")))
    failed = 0
    try:
        by_name = {d.name: d for d in TSC.Pager(server.datasources)}
        for name, incremental in plan(args.mode):
            item = by_name.get(name)
            if item is None:
                print(f"FAIL  {name}: not published")
                failed += 1
                continue
            job = server.datasources.refresh(item, incremental=incremental)
            if job is None:
                print(f"skip  {name}: a refresh is already running")
                continue
            if not args.no_wait:
                server.jobs.wait_for_job(job)
            print(f"ok    {name} ({'incremental' if incremental else 'full'})", flush=True)
    finally:
        server.auth.sign_out()
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
