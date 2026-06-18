import os
from typing import List, Optional

import google.auth
import google.auth.transport.requests
import requests
from google.cloud import migrationcenter_v1
from google.adk.tools import ToolContext


async def list_migration_center_groups(tool_context: ToolContext) -> str:
    """Lists all existing groups in the Migration Center project.
    
    Returns:
        A list of group names and their display names.
    """
    project_id = os.environ.get("GCP_PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT")
    location = os.environ.get("GCP_LOCATION") or os.environ.get("GOOGLE_CLOUD_LOCATION") or "us-central1"

    if location == "global":
        location = "us-central1"

    if not project_id:
        try:
            _, project_id = google.auth.default()
        except Exception as e:
            return f"Error: Failed to get GCP project ID: {e}"

    try:
        client = migrationcenter_v1.MigrationCenterClient()
        parent = f"projects/{project_id}/locations/{location}"
        
        groups = client.list_groups(parent=parent)
        group_list = []
        for group in groups:
            group_list.append(f"- ID: {group.name.split('/')[-1]}, Display Name: {group.display_name}")
        
        if not group_list:
            return "No existing groups found in Migration Center."
        
        return "Existing Groups:\n" + "\n".join(group_list)
    except Exception as e:
        return f"Error listing groups: {e}"


async def assign_assets_to_groups(
    group_id: str, 
    asset_ids: List[str], 
    tool_context: ToolContext,
    group_display_name: Optional[str] = None
) -> str:
    """Assigns specific assets to a group in Migration Center using native APIs.
    
    If the group does not exist, it will be created.

    Args:
        group_id: The ID of the group (e.g., 'web-servers').
        asset_ids: A list of asset IDs to add to the group.
        tool_context: The ADK tool context.
        group_display_name: Optional display name for the group if it needs to be created.

    Returns:
        A string summary of the execution result.
    """
    logs = []
    def log(msg: str):
        print(msg)
        logs.append(msg)

    project_id = os.environ.get("GCP_PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT")
    location = os.environ.get("GCP_LOCATION") or os.environ.get("GOOGLE_CLOUD_LOCATION") or "us-central1"

    if location == "global":
        location = "us-central1"

    if not project_id:
        try:
            _, project_id = google.auth.default()
        except Exception as e:
            return f"Error: Failed to get default GCP project ID: {e}"

    log(f"Using project: {project_id}, location: {location}")

    # Get token for REST API (addAssets is often more reliable via REST for bulk)
    try:
        credentials, _ = google.auth.default()
        auth_req = google.auth.transport.requests.Request()
        credentials.refresh(auth_req)
        token = credentials.token
    except Exception as e:
        return f"Error: Failed to get access token: {e}"

    try:
        client = migrationcenter_v1.MigrationCenterClient()
        parent = f"projects/{project_id}/locations/{location}"
        group_name = f"{parent}/groups/{group_id}"

        # 1. Ensure Group Exists
        try:
            client.get_group(name=group_name)
            log(f"Group {group_id} already exists.")
        except Exception:
            log(f"Group {group_id} not found. Creating...")
            try:
                new_group = migrationcenter_v1.Group(display_name=group_display_name or group_id)
                req = migrationcenter_v1.CreateGroupRequest(
                    parent=parent,
                    group=new_group,
                    group_id=group_id
                )
                op = client.create_group(request=req)
                res = op.result()
                log(f"Group {group_id} created successfully: {res.name}")
            except Exception as ce:
                return f"Error: Failed to create group {group_id}: {ce}"

        # 2. Add Assets to Group
        if not asset_ids:
            return f"Group '{group_id}' is ready, but no assets were provided to add."

        log(f"Adding {len(asset_ids)} assets to group '{group_id}'...")
        
        # We need the full asset names
        # Most of the time users provide IDs, so we might need to resolve them
        # but if we assume they are already full names or IDs in the right format:
        full_asset_names = []
        for aid in asset_ids:
            if aid.startswith("projects/"):
                full_asset_names.append(aid)
            else:
                full_asset_names.append(f"{parent}/assets/{aid}")

        url = f"https://migrationcenter.googleapis.com/v1/{group_name}:addAssets"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        body = {
            "assets": {
                "assetIds": full_asset_names
            },
            "allowExisting": True
        }
        
        resp = requests.post(url, headers=headers, json=body)
        if resp.status_code == 200:
             log(f"Successfully added assets to '{group_id}' group.")
             return f"Success: Added {len(asset_ids)} assets to group '{group_id}'.\n" + "\n".join(logs)
        else:
             error_msg = f"Failed to add assets to group: {resp.status_code} - {resp.text}"
             log(error_msg)
             return error_msg

    except Exception as e:
        return f"Error in group assignment: {e}\nLogs so far:\n" + "\n".join(logs)
