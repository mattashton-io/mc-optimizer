import io
import os

import google.auth
import google.auth.transport.requests
import pandas as pd
import requests
from google.adk.tools import ToolContext
from google.cloud import migrationcenter_v1

from .app_utils.project_utils import get_project_id


async def list_migration_center_groups(tool_context: ToolContext) -> str:
    """Lists all existing groups in the Migration Center project.

    Returns:
        A list of group names and their display names.
    """
    project_id = get_project_id()
    location = (
        os.environ.get("GCP_LOCATION")
        or os.environ.get("GOOGLE_CLOUD_LOCATION")
        or "us-central1"
    )

    if location == "global":
        location = "us-central1"

    if not project_id:
        return "Error: GCP Project ID could not be determined."

    try:
        client = migrationcenter_v1.MigrationCenterClient()
        parent = f"projects/{project_id}/locations/{location}"

        groups = client.list_groups(parent=parent)
        group_list = []
        for group in groups:
            group_list.append(
                f"- ID: {group.name.split('/')[-1]}, Display Name: {group.display_name}"
            )

        if not group_list:
            return "No existing groups found in Migration Center."

        return "Existing Groups:\n" + "\n".join(group_list)
    except Exception as e:
        return f"Error listing groups: {e}"


async def assign_assets_to_groups(
    group_id: str,
    asset_ids: list[str] | None = None,
    tool_context: ToolContext | None = None,
    group_display_name: str | None = None,
) -> str:
    """Assigns specific assets to a group in Migration Center using native APIs.

    If asset_ids is not provided, it will attempt to assign ALL unique VMs from the 'vmInfo.csv' artifact.
    If the group does not exist, it will be created.

    Args:
        group_id: The ID of the group (e.g., 'all-servers').
        asset_ids: Optional list of asset IDs to add. If None, uses all unique VMs from current session.
        tool_context: The ADK tool context.
        group_display_name: Optional display name for the group.
    """
    logs = []

    def log(msg: str):
        print(msg)
        logs.append(msg)

    project_id = get_project_id()
    location = (
        os.environ.get("GCP_LOCATION")
        or os.environ.get("GOOGLE_CLOUD_LOCATION")
        or "us-central1"
    )
    if location == "global":
        location = "us-central1"

    if not project_id:
        return "Error: GCP Project ID could not be determined."

    log(f"Using project: {project_id}, location: {location}")

    # 1. Resolve Asset IDs if not provided (Automatic "all-servers" grouping)
    final_asset_ids = asset_ids or []
    if not final_asset_ids:
        log(
            "No asset_ids provided. Attempting to load all unique VMs from session artifacts..."
        )
        try:
            part = await tool_context.load_artifact("vmInfo.csv")
            if part:
                content = part.text or part.inline_data.data.decode("utf-8")
                df = pd.read_csv(io.StringIO(content))
                if "MachineId" in df.columns:
                    raw_ids = df["MachineId"].dropna().unique().tolist()
                    final_asset_ids = [
                        str(aid).strip() for aid in raw_ids if str(aid).strip()
                    ]
                    log(f"Found {len(final_asset_ids)} unique assets in session.")
            else:
                log("No 'vmInfo.csv' artifact found to resolve assets automatically.")
        except Exception as e:
            log(f"Warning: Failed to load assets from artifact: {e}")
    else:
        final_asset_ids = [
            str(aid).strip()
            for aid in final_asset_ids
            if pd.notna(aid) and str(aid).strip()
        ]

    if not final_asset_ids:
        return "Error: No assets found to assign to group."

    # 2. API Setup
    try:
        credentials, _ = google.auth.default()
        auth_req = google.auth.transport.requests.Request()
        credentials.refresh(auth_req)
        token = credentials.token
        client = migrationcenter_v1.MigrationCenterClient()
    except Exception as e:
        return f"Error: API client setup failed: {e}"

    parent = f"projects/{project_id}/locations/{location}"
    group_name = f"{parent}/groups/{group_id}"

    # 3. Ensure Group Exists
    try:
        client.get_group(name=group_name)
        log(f"Group '{group_id}' already exists.")
    except Exception:
        log(f"Group '{group_id}' not found. Creating...")
        try:
            new_group = migrationcenter_v1.Group(
                display_name=group_display_name or group_id
            )
            client.create_group(
                request=migrationcenter_v1.CreateGroupRequest(
                    parent=parent, group=new_group, group_id=group_id
                )
            ).result()
            log(f"Group '{group_id}' created successfully.")
        except Exception as ce:
            return f"Error: Failed to create group {group_id}: {ce}"

    # 4. Add Assets to Group
    log(f"Adding {len(final_asset_ids)} assets to group '{group_id}'...")

    full_asset_names = []
    for aid in final_asset_ids:
        if aid.startswith("projects/"):
            full_asset_names.append(aid)
        else:
            full_asset_names.append(f"{parent}/assets/{aid}")

    url = f"https://migrationcenter.googleapis.com/v1/{group_name}:addAssets"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    body = {"assets": {"assetIds": full_asset_names}, "allowExisting": True}

    try:
        resp = requests.post(url, headers=headers, json=body)
        if resp.status_code == 200:
            return (
                f"Success: Assigned {len(final_asset_ids)} assets to group '{group_id}'.\n"
                + "\n".join(logs)
            )
        else:
            return f"Error: API failed with {resp.status_code}: {resp.text}"
    except Exception as e:
        return f"Error: Request failed: {e}"
