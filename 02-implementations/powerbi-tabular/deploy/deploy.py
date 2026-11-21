"""Deploy the S2 semantic models to a Fabric workspace and refresh them (SPEC E5, E6).

1. fabric-cicd publishes the selected models from models/ with deploy/parameter.yml (environment tokens and
   connection bindings resolved from environment variables).
2. Each published model is refreshed through the Power BI REST API with an enhanced refresh that applies the
   incremental refresh policy (applyRefreshPolicy: monthly partitions are created, merged and retired by the service;
   the hybrid policy keeps the newest day in DirectQuery). For Direct Lake models the same call reframes the model.

    python deploy.py --environment test --workspace-id <guid> --variants import directlake directquery

Authentication uses azure-identity DefaultAzureCredential (in GitHub Actions: workload identity federation through
azure/login, or AZURE_CLIENT_ID / AZURE_TENANT_ID / AZURE_CLIENT_SECRET).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import requests
from azure.identity import DefaultAzureCredential

HERE = Path(__file__).resolve().parent
MODELS = HERE.parent / "models"
PBI = "https://api.powerbi.com/v1.0/myorg"
PBI_SCOPE = "https://analysis.windows.net/powerbi/api/.default"
VARIANT_SUFFIX = {"import": "Import", "directlake": "DirectLake", "directquery": "DirectQuery"}
TERMINAL = {"Completed", "Failed", "Cancelled", "Disabled"}


def model_names(variants: list[str]) -> list[str]:
    names = [f"SLC_{ds}_{VARIANT_SUFFIX[v]}" for ds in ("WWI", "NYC") for v in variants]
    missing = [n for n in names if not (MODELS / f"{n}.SemanticModel").is_dir()]
    if missing:
        raise SystemExit(f"models not found in {MODELS}: {missing}")
    return names


def publish(environment: str, workspace_id: str, names: list[str], credential) -> None:
    from fabric_cicd import FabricWorkspace, append_feature_flag, publish_all_items

    append_feature_flag("enable_environment_variable_replacement")
    append_feature_flag("enable_items_to_include")
    workspace = FabricWorkspace(
        workspace_id=workspace_id,
        repository_directory=str(MODELS),
        item_type_in_scope=["SemanticModel"],
        environment=environment,
        token_credential=credential,
        parameter_file_path=str(HERE / "parameter.yml"),
    )
    publish_all_items(workspace, items_to_include=[f"{n}.SemanticModel" for n in names])


def dataset_ids(session: requests.Session, workspace_id: str, names: list[str]) -> dict[str, str]:
    r = session.get(f"{PBI}/groups/{workspace_id}/datasets", timeout=60)
    r.raise_for_status()
    found = {d["name"]: d["id"] for d in r.json()["value"]}
    missing = [n for n in names if n not in found]
    if missing:
        raise SystemExit(f"published models not visible in the workspace: {missing}")
    return {n: found[n] for n in names}


def refresh(session: requests.Session, workspace_id: str, name: str, dataset_id: str, timeout_s: int) -> str:
    url = f"{PBI}/groups/{workspace_id}/datasets/{dataset_id}/refreshes"
    r = session.post(url, json={"type": "full", "commitMode": "transactional", "applyRefreshPolicy": True}, timeout=60)
    if r.status_code not in (200, 202):
        raise SystemExit(f"{name}: refresh request failed {r.status_code}: {r.text[:300]}")
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        time.sleep(30)
        latest = session.get(url, params={"$top": 1}, timeout=60)
        latest.raise_for_status()
        status = latest.json()["value"][0]["status"]
        print(f"{name}: refresh {status}", flush=True)
        if status in TERMINAL:
            return status
    return "TimedOut"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--environment", required=True, choices=["test", "prod"])
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--variants", nargs="+", default=list(VARIANT_SUFFIX), choices=list(VARIANT_SUFFIX))
    parser.add_argument("--refresh-timeout", type=int, default=7200, help="seconds per model")
    parser.add_argument("--skip-refresh", action="store_true")
    args = parser.parse_args()

    names = model_names(args.variants)
    credential = DefaultAzureCredential()
    publish(args.environment, args.workspace_id, names, credential)
    if args.skip_refresh:
        return
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {credential.get_token(PBI_SCOPE).token}"
    failed = []
    for name, dataset_id in dataset_ids(session, args.workspace_id, names).items():
        status = refresh(session, args.workspace_id, name, dataset_id, args.refresh_timeout)
        if status != "Completed":
            failed.append(f"{name}: {status}")
    if failed:
        print("refresh failures: " + "; ".join(failed))
        sys.exit(1)


if __name__ == "__main__":
    main()
