import io
import os
import re

import pandas as pd
from google.adk.tools import ToolContext
from google.cloud import migrationcenter_v1
from google.protobuf import field_mask_pb2

from .app_utils.project_utils import get_project_id


async def add_labels_post_import(
    tool_context: ToolContext, labels_dict: dict[str, dict[str, str]] | None = None
) -> str:
    """Updates labels for assets in Migration Center using native APIs.

    If labels_dict is not provided, it reads from the 'staged_labels.csv' session artifact.
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
                log(
                    f"Loaded labels for {len(final_labels_dict)} assets from session artifact."
                )
        except Exception as e:
            log(f"Warning: Failed to load staged labels: {e}")

    if not final_labels_dict:
        return "Info: No labels found to apply."

    # 2. Setup MC Client
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

    try:
        client = migrationcenter_v1.MigrationCenterClient()
        parent = f"projects/{project_id}/locations/{location}"

        log("Listing assets from Migration Center...")
        assets = client.list_assets(parent=parent)

        updated_count = 0
        skipped_count = 0
        errors = []

        def normalize_key(k: str) -> str:
            # GCP Labels: Lowercase, alphanumeric, underscores or hyphens.
            # Must start with a lowercase letter. Max 63 chars.
            clean = re.sub(r"[^a-z0-9_-]", "_", k.lower())
            if clean and not clean[0].islower():
                clean = "l_" + clean
            return clean[:63]

        # 3. Process Updates per Asset
        for asset in assets:
            asset_full_name = asset.name
            asset_id = asset.name.split("/")[-1].lower()

            # Find metadata for this asset (case-insensitive ID match)
            new_labels = None
            for m_id, labels in final_labels_dict.items():
                if m_id.lower() == asset_id:
                    new_labels = labels
                    break

            if not new_labels:
                continue

            current_labels = dict(asset.labels) if asset.labels else {}
            needs_update = False

            for raw_k, raw_v in new_labels.items():
                k_norm = normalize_key(raw_k)
                v_str = str(raw_v).lower()[:63]
                v_norm = re.sub(r"[^a-z0-9_-]", "_", v_str)

                if current_labels.get(k_norm) != v_norm:
                    current_labels[k_norm] = v_norm
                    needs_update = True

            if needs_update:
                log(f"Updating labels for asset {asset_id}...")
                try:
                    updated_asset = migrationcenter_v1.Asset()
                    updated_asset.name = asset_full_name
                    for k, v in current_labels.items():
                        updated_asset.labels[k] = v

                    update_mask = field_mask_pb2.FieldMask(paths=["labels"])
                    client.update_asset(
                        request=migrationcenter_v1.UpdateAssetRequest(
                            asset=updated_asset, update_mask=update_mask
                        )
                    )
                    updated_count += 1
                except Exception as ex:
                    errors.append(f"Failed {asset_id}: {ex}")
            else:
                skipped_count += 1

        summary = (
            f"Labeling Complete. Updated: {updated_count}, Skipped: {skipped_count}."
        )
        if errors:
            summary += f" Errors: {len(errors)}"
        return summary + "\nLogs:\n" + "\n".join(logs)

    except Exception as e:
        return f"Error: Failed post-import labeling: {e}"
