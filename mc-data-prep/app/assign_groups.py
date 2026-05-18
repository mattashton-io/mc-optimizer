import os
import pandas as pd
import google.auth
import google.auth.transport.requests
import requests
from google.cloud import migrationcenter_v1

def assign_assets_to_groups() -> str:
    """Assigns Migration Center assets to groups based on their source (VMware vs Hyper-V) as defined in tagInfo.csv.
    
    Returns:
        A string summary of the execution log.
    """
    logs = []
    def log(msg: str):
        print(msg)
        logs.append(msg)

    tag_file = os.path.join(os.path.dirname(__file__), "data", "output", "tagInfo.csv")
        
    if not os.path.exists(tag_file):
        return f"Error: tagInfo.csv not found at {tag_file}. Please run data prep first."

    try:
        df_tags = pd.read_csv(tag_file)
    except Exception as e:
        return f"Error: Failed to read {tag_file}: {e}"
    
    project_id = os.environ.get("GCP_PROJECT_ID")
    location = os.environ.get("GCP_LOCATION", "us-central1")
    
    if not project_id:
        try:
            _, project_id = google.auth.default()
        except Exception as e:
            return f"Error: Failed to get default GCP project ID: {e}"
            
    if not project_id:
        return "Error: GCP_PROJECT_ID environment variable not set and could not be determined."

    log(f"Using project: {project_id}, location: {location}")

    # Get access token for REST API fallback
    log("Getting access token...")
    try:
        credentials, _ = google.auth.default()
        credentials.refresh(google.auth.transport.requests.Request())
        token = credentials.token
    except Exception as e:
        return f"Error: Failed to get access token: {e}"

    try:
        client = migrationcenter_v1.MigrationCenterClient()
        parent = f"projects/{project_id}/locations/{location}"

        groups = {
            "vmware": "vmware-assets",
            "hyperv": "hyperv-assets"
        }

        created_groups = {}

        for key, group_id in groups.items():
            group_name = f"{parent}/groups/{group_id}"
            log(f"Checking if group {group_id} exists...")
            try:
                group = client.get_group(name=group_name)
                log(f"Group {group_id} already exists.")
                created_groups[key] = group_name
            except Exception:
                log(f"Group {group_id} not found. Attempting to create...")
                try:
                    new_group = migrationcenter_v1.Group(display_name=group_id)
                    req = migrationcenter_v1.CreateGroupRequest(
                        parent=parent,
                        group=new_group,
                        group_id=group_id
                    )
                    op = client.create_group(request=req)
                    res = op.result()
                    log(f"Group {group_id} created successfully: {res.name}")
                    created_groups[key] = res.name
                except Exception as ce:
                    return f"Error: Failed to create group {group_id}: {ce}\nLogs so far:\n" + "\n".join(logs)

        # List all assets
        log("Listing assets from Migration Center...")
        assets = client.list_assets(parent=parent)
        
        vmware_assets = []
        hyperv_assets = []

        for asset in assets:
            # Try to match asset to MachineId
            asset_id = asset.name.split('/')[-1]
            matched = False
            for _, row in df_tags.iterrows():
                m_id = str(row["MachineId"])
                source = row["Value"]
                
                if asset_id == m_id:
                    if source == "vmware":
                        vmware_assets.append(asset.name)
                    elif source == "hyperv":
                        hyperv_assets.append(asset.name)
                    matched = True
                    break
                    
            if not matched:
                # Only print if it doesn't look like a generated ID we know about to reduce noise
                if "uuid" not in asset.name and "hv-vm" not in asset.name:
                     log(f"Could not match asset {asset.name} to any MachineId in tagInfo.csv")

        # Add assets to groups using REST API fallback
        def add_assets(group_name, asset_list, group_label) -> str:
            if not asset_list:
                log(f"No assets to add to {group_label}.")
                return f"No assets to add to {group_label}."
            log(f"Adding {len(asset_list)} assets to {group_label} group...")
            url = f"https://migrationcenter.googleapis.com/v1/{group_name}:addAssets"
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            body = {
                "assets": {
                    "assetIds": asset_list
                },
                "allowExisting": True
            }
            try:
                resp = requests.post(url, headers=headers, json=body)
                if resp.status_code == 200:
                     log(f"Successfully added assets to {group_label} group.")
                     return "Success"
                else:
                     error_msg = f"Failed to add assets to {group_label} group: {resp.status_code} - {resp.text}"
                     log(error_msg)
                     return error_msg
            except Exception as e:
                error_msg = f"Failed to add assets to {group_label} group: {e}"
                log(error_msg)
                return error_msg

        vmware_res = add_assets(created_groups["vmware"], vmware_assets, "vmware-assets")
        hyperv_res = add_assets(created_groups["hyperv"], hyperv_assets, "hyperv-assets")
        
        if "Failed" in vmware_res or "Failed" in hyperv_res:
            return "Completed with errors.\n" + "\n".join(logs)
        
        return "Successfully completed group assignment.\n" + "\n".join(logs)
                
    except Exception as e:
        return f"Error: Failed to list assets or process groups: {e}\nLogs:\n" + "\n".join(logs)

if __name__ == "__main__":
    print(assign_assets_to_groups())
