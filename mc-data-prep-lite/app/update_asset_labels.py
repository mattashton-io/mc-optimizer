import os
import re
import io
from typing import Dict, Optional

import google.auth
import google.auth.transport.requests
from google.cloud import migrationcenter_v1
from google.protobuf import field_mask_pb2
from google.adk.tools import ToolContext
import pandas as pd


async def add_labels_post_import(
    tool_context: ToolContext,
    labels_dict: Optional[Dict[str, Dict[str, str]]] = None
) -> str:
    """Updates labels for assets in Migration Center using native APIs.

    If labels_dict is not provided, it reads from the 'staged_labels.csv' session artifact.

    Args:
        tool_context: The ADK tool context.
        labels_dict: Optional dictionary mapping MachineId to labels {key: value}.
    """
    logs = []

    def log(msg: str):
        print(msg)
        logs.append(msg)

    # 1. Resolve Labels to Apply
    final_labels_dict = labels_dict or {}

    if not final_labels_dict:
        log("No labels_dict provided. Checking 'staged_labels.csv' artifact...")
        try:
            part = await tool_context.load_artifact("staged_labels.csv")
            if part:
                content = part.text or part.inline_data.data.decode("utf-8")
                df = pd.read_csv(io.StringIO(content))
                for _, row in df.iterrows():
                    m_id = str(row["MachineId"]).strip()
                    k = str(row["Key"]).strip()
                    v = str(row["Value"]).strip()
                    if m_id not in final_labels_dict:
                        final_labels_dict[m_id] = {}
                    final_labels_dict[m_id][k] = v
                log(f"Loaded labels for {len(final_labels_dict)} assets from session artifact.")
            else:
                log("No 'staged_labels.csv' artifact found.")
        except Exception as e:
            log(f"Warning: Failed to load staged labels from artifact: {e}")

    if not final_labels_dict:
        return "Info: No labels found to apply. Please run 'process_uploaded_infrastructure_file' or 'add_labels_to_staged_artifact' first."

    # 2. Setup GCS/MC Client
    project_id = os.environ.get("GCP_PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT")
    location = os.environ.get("GCP_LOCATION") or os.environ.get("GOOGLE_CLOUD_LOCATION") or "us-central1"
    if location == "global": location = "us-central1"

    if not project_id:
        try:
            _, project_id = google.auth.default()
        except Exception:
            return "Error: GCP_PROJECT_ID not set."

    log(f"Using project: {project_id}, location: {location}")

    try:
        client = migrationcenter_v1.MigrationCenterClient()
        parent = f"projects/{project_id}/locations/{location}"

        log("Listing assets from Migration Center...")
        assets = client.list_assets(parent=parent)

        updated_count = 0
        skipped_count = 0
        errors = []

        # 3. Normalize Input
        norm_dict = {}
        for m_id, labels in final_labels_dict.items():
            mid_low = m_id.lower()
            norm_labels = {}
            for k, v in labels.items():
                k_clean = re.sub(r"[^a-z0-9_-]", "_", k.lower())
                if k_clean and not k_clean[0].islower(): k_clean = "l_" + k_clean
                v_clean = re.sub(r"[^a-z0-9_-]", "_", str(v).lower())
                norm_labels[k_clean[:63]] = v_clean[:63]
            norm_dict[mid_low] = norm_labels

        # 4. Apply Labels via API
        for asset in assets:
            asset_full_name = asset.name
            asset_id = asset.name.split("/")[-1].lower()
            
            # Match by MachineId or common UUID patterns in MC
            matched_labels = norm_dict.get(asset_id)
            
            if matched_labels:
                current_labels = dict(asset.labels) if asset.labels else {}
                needs_update = False
                for k, v in matched_labels.items():
                    if current_labels.get(k) != v:
                        current_labels[k] = v
                        needs_update = True

                if needs_update:
                    log(f"Updating asset {asset_id}...")
                    try:
                        updated_asset = migrationcenter_v1.Asset()
                        updated_asset.name = asset_full_name
                        for k, v in current_labels.items():
                            updated_asset.labels[k] = v
                        
                        update_mask = field_mask_pb2.FieldMask(paths=["labels"])
                        client.update_asset(request=migrationcenter_v1.UpdateAssetRequest(
                            asset=updated_asset, update_mask=update_mask
                        ))
                        updated_count += 1
                    except Exception as ex:
                        errors.append(f"Failed {asset_id}: {ex}")
                else:
                    skipped_count += 1

        summary = f"API Labeling Complete. Updated: {updated_count}, Skipped: {skipped_count}."
        if errors: summary += f" Errors: {len(errors)}"
        return summary + "\nLogs:\n" + "\n".join(logs)

    except Exception as e:
        return f"Error: Failed post-import labeling: {e}"
