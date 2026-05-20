import os
import re
import pandas as pd
import google.auth
import google.auth.transport.requests
from google.cloud import migrationcenter_v1
from google.protobuf import field_mask_pb2

def add_labels_post_import() -> str:
    """Retrieves assets from Migration Center and updates their labels post-import based on tagInfo.csv.
    
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
        df = pd.read_csv(tag_file)
    except Exception as e:
        return f"Error: Failed to read {tag_file}: {e}"

    if df.empty:
        return f"Info: tagInfo.csv is empty. No labels to apply."

    # Identify columns robustly
    id_col = None
    for col in ["Machine Id", "MachineId", "Machine ID", "machine_id", "machine id"]:
        if col in df.columns:
            id_col = col
            break
    if not id_col:
        id_col = df.columns[0]

    key_col = None
    for col in ["Tag Category", "Key", "Category", "tag_category", "key"]:
        if col in df.columns:
            key_col = col
            break
    if not key_col:
        key_col = df.columns[1] if len(df.columns) > 1 else None

    val_col = None
    for col in ["Tag Value", "Value", "tag_value", "value"]:
        if col in df.columns:
            val_col = col
            break
    if not val_col:
        val_col = df.columns[2] if len(df.columns) > 2 else None

    log(f"Mapping columns - ID: '{id_col}', Key: '{key_col}', Value: '{val_col}'")

    # Group labels by Machine ID and clean keys/values to conform to GCP label requirements:
    # Keys/values must contain only lowercase letters, numeric characters, underscores, and dashes.
    # Keys must start with a lowercase letter or international character. Max 63 characters.
    labels_by_machine = {}
    for _, row in df.iterrows():
        m_id = str(row[id_col]).strip()
        k = str(row[key_col]).strip() if key_col else ""
        v = str(row[val_col]).strip() if val_col else ""
        if not m_id or not k:
            continue
        
        # Clean key
        k_clean = re.sub(r'[^a-z0-9_-]', '_', k.lower())
        if k_clean and not k_clean[0].islower():
            k_clean = 'l_' + k_clean
        k_clean = k_clean[:63]
        
        # Clean value
        v_clean = re.sub(r'[^a-z0-9_-]', '_', v.lower())
        v_clean = v_clean[:63]

        if m_id not in labels_by_machine:
            labels_by_machine[m_id] = {}
        labels_by_machine[m_id][k_clean] = v_clean

    # Robust environment variable detection
    project_id = os.environ.get("GCP_PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT")
    location = os.environ.get("GCP_LOCATION") or os.environ.get("GOOGLE_CLOUD_LOCATION") or "us-central1"
    
    if location == "global":
        location = "us-central1"
    
    if not project_id:
        try:
            _, project_id = google.auth.default()
        except Exception as e:
            return f"Error: Failed to get default GCP project ID: {e}"
            
    if not project_id:
        return "Error: GCP_PROJECT_ID or GOOGLE_CLOUD_PROJECT environment variable not set and could not be determined."

    log(f"Using project: {project_id}, location: {location}")

    try:
        client = migrationcenter_v1.MigrationCenterClient()
        parent = f"projects/{project_id}/locations/{location}"

        # List all assets
        log("Listing assets from Migration Center...")
        assets = client.list_assets(parent=parent)
        
        updated_count = 0
        skipped_count = 0
        unmatched_count = 0
        errors = []

        for asset in assets:
            asset_id = asset.name.split('/')[-1]
            
            # Match asset to Machine ID from CSV
            matched_id = None
            for m_id in labels_by_machine:
                if asset_id == m_id or asset_id.lower() == m_id.lower():
                    matched_id = m_id
                    break
            
            if matched_id:
                new_labels = labels_by_machine[matched_id]
                current_labels = dict(asset.labels) if asset.labels else {}
                
                # Check for changes
                needs_update = False
                for k, v in new_labels.items():
                    if current_labels.get(k) != v:
                        current_labels[k] = v
                        needs_update = True
                
                if needs_update:
                    log(f"Updating labels for asset {asset_id} to: {current_labels}")
                    try:
                        updated_asset = migrationcenter_v1.Asset()
                        updated_asset.name = asset.name
                        # Protobuf map fields don't support direct assignment: updated_asset.labels = current_labels
                        # Instead, use .update() or individual key assignment
                        for k, v in current_labels.items():
                            updated_asset.labels[k] = v
                        
                        update_mask = field_mask_pb2.FieldMask(paths=["labels"])
                        
                        req = migrationcenter_v1.UpdateAssetRequest(
                            asset=updated_asset,
                            update_mask=update_mask
                        )
                        
                        op = client.update_asset(request=req)
                        op.result() # block on LRO resolution
                        log(f"Asset {asset_id} updated successfully.")
                        updated_count += 1
                    except Exception as ex:
                        error_msg = f"Failed to update asset {asset_id}: {ex}"
                        log(error_msg)
                        errors.append(error_msg)
                else:
                    log(f"Asset {asset_id} already has all matching labels. Skipping.")
                    skipped_count += 1
            else:
                # Log unmatched assets to help debug if MachineIds are not what we expect
                if "uuid" not in asset_id.lower() and "hv-vm" not in asset_id.lower():
                    log(f"Asset {asset_id} not found in tagInfo.csv. Skipping labeling.")
                unmatched_count += 1

        summary = (
            f"Post-Import Labeling Complete.\n"
            f"Successfully updated: {updated_count} assets.\n"
            f"Skipped (already matching): {skipped_count} assets.\n"
            f"Unmatched in CSV: {unmatched_count} assets.\n"
        )
        if errors:
            summary += f"Errors encountered: {len(errors)}\n"
        
        return summary + "\nLogs:\n" + "\n".join(logs)
                
    except Exception as e:
        return f"Error: Failed to process post-import asset labeling: {e}\nLogs:\n" + "\n".join(logs)

if __name__ == "__main__":
    print(add_labels_post_import())
