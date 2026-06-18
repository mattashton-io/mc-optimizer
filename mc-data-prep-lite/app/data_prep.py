import io
import os
import re

import numpy as np
import pandas as pd
from google.adk.tools import ToolContext
from google.genai import types


async def process_uploaded_infrastructure_file(
    artifact_id: str, format_type: str, tool_context: ToolContext
) -> str:
    """Processes an infrastructure export file in memory and saves it as session artifacts.

    This tool transforms the data and saves 'vmInfo.csv', 'diskInfo.csv', and 'tagInfo.csv'
    as artifacts in the current session.

    Args:
        artifact_id: The ID (filename) of the artifact in the ADK chat.
        format_type: The source format ('vmware' or 'hyperv').

    Returns:
        A summary of the processed data.
    """
    try:
        part = await tool_context.load_artifact(artifact_id)
        if not part:
            return f"Error: Artifact '{artifact_id}' not found."

        file_bytes = None
        if part.inline_data:
            file_bytes = part.inline_data.data
        elif part.text:
            file_bytes = part.text.encode("utf-8")

        if not file_bytes:
            return f"Error: Could not retrieve data for artifact '{artifact_id}'."

        # In-memory processing
        if format_type.lower() == "vmware":
            if artifact_id.lower().endswith(".xlsx"):
                with io.BytesIO(file_bytes) as f:
                    try:
                        df_info = pd.read_excel(f, sheet_name="vInfo")
                        f.seek(0)
                        df_disk = pd.read_excel(f, sheet_name="vDisk")
                    except Exception:
                        return "Error: Could not find 'vInfo' or 'vDisk' sheets in the Excel file."
            else:
                with io.BytesIO(file_bytes) as f:
                    df_info = pd.read_csv(f)
                    df_disk = pd.DataFrame()
        elif format_type.lower() == "hyperv":
            with io.BytesIO(file_bytes) as f:
                df_info = pd.read_csv(f)
                df_disk = pd.DataFrame()
        else:
            return f"Error: Unsupported format type '{format_type}'."

        # Perform transformation logic
        transformed = _transform_in_memory(df_info, df_disk, format_type.lower())

        # Save as artifacts
        await tool_context.save_artifact(
            "vmInfo.csv", types.Part(text=transformed["vms"].to_csv(index=False))
        )
        await tool_context.save_artifact(
            "diskInfo.csv", types.Part(text=transformed["disks"].to_csv(index=False))
        )
        await tool_context.save_artifact(
            "tagInfo.csv", types.Part(text=transformed["tags"].to_csv(index=False))
        )

        return (
            f"Successfully processed {len(transformed['vms'])} VMs from {format_type}. "
            f"Transformed files (vmInfo.csv, diskInfo.csv, tagInfo.csv) have been saved as session artifacts. "
            f"You can now run 'get_parsed_vms' to review or 'import_data_to_migration_center' to proceed."
        )

    except Exception as e:
        return f"Error processing artifact: {e}"


async def get_parsed_vms(tool_context: ToolContext) -> str:
    """Retrieves the list of parsed VMs from the 'vmInfo.csv' session artifact."""
    try:
        part = await tool_context.load_artifact("vmInfo.csv")
        if not part:
            return "Error: 'vmInfo.csv' artifact not found. Please run 'process_uploaded_infrastructure_file' first."

        content = part.text or part.inline_data.data.decode("utf-8")
        df = pd.read_csv(io.StringIO(content))
        cols = [
            "MachineId",
            "MachineName",
            "OsType(optional)",
            "MachineTypeLabel(optional)",
        ]
        cols = [c for c in cols if c in df.columns]
        return df[cols].to_csv(index=False)
    except Exception as e:
        return f"Error retrieving parsed VMs: {e}"


async def add_labels_to_tag_file(
    machine_ids: list[str], key: str, value: str, tool_context: ToolContext
) -> str:
    """Adds or updates a label (key-value pair) for a list of machine IDs in the 'tagInfo.csv' session artifact."""
    try:
        part = await tool_context.load_artifact("tagInfo.csv")
        if not part:
            # Create a new tag file if it doesn't exist
            tags_df = pd.DataFrame(columns=["MachineId", "Key", "Value"])
        else:
            content = part.text or part.inline_data.data.decode("utf-8")
            tags_df = pd.read_csv(io.StringIO(content))

        id_col = "MachineId"
        key_col = "Key"
        val_col = "Value"

        new_rows = []
        for mid in machine_ids:
            if (
                not tags_df.empty
                and id_col in tags_df.columns
                and key_col in tags_df.columns
            ):
                tags_df = tags_df[~((tags_df[id_col] == mid) & (tags_df[key_col] == key))]
            new_rows.append({id_col: mid, key_col: key, val_col: value})

        if new_rows:
            new_df = pd.DataFrame(new_rows)
            tags_df = pd.concat([tags_df, new_df], ignore_index=True)

        await tool_context.save_artifact(
            "tagInfo.csv", types.Part(text=tags_df.to_csv(index=False))
        )
        return f"Successfully added/updated label '{key}={value}' for {len(machine_ids)} servers in session artifacts."
    except Exception as e:
        return f"Error updating labels: {e}"


def _transform_in_memory(
    df_info: pd.DataFrame, df_disk: pd.DataFrame, source_type: str
) -> dict[str, pd.DataFrame]:
    def clean_number(val):
        if pd.isna(val):
            return np.nan
        if isinstance(val, str):
            val = val.replace(",", "").replace('"', "")
            try:
                return float(val)
            except ValueError:
                return np.nan
        return float(val)

    def extract_vm_name(path):
        if pd.isna(path):
            return "unknown-vm"
        match = re.search(r"\]\s*([^/]+)/", path)
        if match:
            return match.group(1).strip()
        match = re.search(r"([^/]+)\.(vmx|vmdk)$", path)
        if match:
            name = match.group(1)
            return re.sub(r"_\d+$", "", name)
        return re.sub(r"[^a-zA-Z0-9_-]", "_", str(path))

    def map_os_type(os_name):
        os_name = str(os_name).lower()
        if "windows" in os_name:
            return "Windows"
        if any(x in os_name for x in ["linux", "ubuntu", "rhel", "debian"]):
            return "Linux"
        return "Linux"

    vm_info = pd.DataFrame()
    disk_info = pd.DataFrame()

    if source_type == "vmware":
        df_info["MachineName"] = (
            df_info["Path"].apply(extract_vm_name)
            if "Path" in df_info.columns
            else df_info["VM"]
        )
        df_info["MachineId"] = df_info["MachineName"]
        df_info["MemoryMiB"] = df_info["Memory"].apply(clean_number)
        df_info["MemoryGiB"] = df_info["MemoryMiB"] / 1024.0
        df_info["AllocatedProcessorCoreCount"] = df_info["CPUs"]
        df_info["OsName"] = df_info.get(
            "OS according to the configuration file", df_info.get("OS", "Linux")
        )

        if not df_disk.empty:
            df_disk["Path_Name"] = (
                df_disk["Path"].apply(extract_vm_name)
                if "Path" in df_disk.columns
                else df_disk["VM"]
            )
            df_disk["MachineId"] = df_disk["Path_Name"]
            df_disk["CapacityMiB"] = df_disk["Capacity MiB"].apply(clean_number)
            df_disk["SizeInGib"] = df_disk["CapacityMiB"] / 1024.0
            disk_sum = df_disk.groupby("MachineId")["SizeInGib"].sum().reset_index()
            disk_sum.rename(columns={"SizeInGib": "TotalDiskAllocatedGiB"}, inplace=True)
            df_vm = pd.merge(df_info, disk_sum, on="MachineId", how="left")

            disk_info["MachineId"] = df_disk["MachineId"]
            disk_info["DiskLabel"] = df_disk.get("Disk", "disk-0")
            disk_info["SizeInGib"] = df_disk["SizeInGib"]
            disk_info["UsedInGib"] = 0
            disk_info["StorageTypeLabel"] = df_disk.get("Label", "VMware")
        else:
            df_vm = df_info.copy()
            df_vm["TotalDiskAllocatedGiB"] = 0

        vm_info["MachineId"] = df_vm["MachineId"]
        vm_info["MachineName"] = df_vm["MachineName"]
        vm_info["TotalDiskAllocatedGiB"] = df_vm["TotalDiskAllocatedGiB"]
        vm_info["AllocatedProcessorCoreCount"] = df_vm["AllocatedProcessorCoreCount"]
        vm_info["MemoryGiB"] = df_vm["MemoryGiB"]
        vm_info["OsName"] = df_vm["OsName"]
        vm_info["OsType(optional)"] = df_vm["OsName"].apply(map_os_type)
        vm_info["IsPhysical"] = "FALSE"
        vm_info["MachineTypeLabel(optional)"] = "VMware VM"

    elif source_type == "hyperv":
        df_info["MachineId"] = [f"hv-vm-{i}" for i in range(1, len(df_info) + 1)]
        df_info["MachineName"] = df_info["MachineId"]

        vm_info["MachineId"] = df_info["MachineId"]
        vm_info["MachineName"] = df_info["MachineName"]
        vm_info["TotalDiskAllocatedGiB"] = df_info["TotalDiskAllocatedGiB"]
        vm_info["TotalDiskUsedGiB"] = df_info["TotalDiskUsedGiB"]
        vm_info["AllocatedProcessorCoreCount"] = df_info["AllocatedProcessorCoreCount"]
        vm_info["MemoryGiB"] = df_info["MemoryGiB"]
        vm_info["OsName"] = df_info["OsName"]
        vm_info["OsType(optional)"] = df_info["OsName"].apply(map_os_type)
        vm_info["IsPhysical"] = "FALSE"
        vm_info["MachineTypeLabel(optional)"] = "Hyper-V VM"

        disk_info["MachineId"] = df_info["MachineId"]
        disk_info["DiskLabel"] = "disk-0"
        disk_info["SizeInGib"] = df_info["TotalDiskAllocatedGiB"]
        disk_info["UsedInGib"] = df_info["TotalDiskUsedGiB"]
        disk_info["StorageTypeLabel"] = "Hyper-V"

    tags = pd.DataFrame(columns=["MachineId", "Key", "Value"])
    tags["MachineId"] = vm_info["MachineId"]
    tags["Key"] = "source"
    tags["Value"] = source_type

    return {"vms": vm_info, "disks": disk_info, "tags": tags}


def upload_file_to_gcs(local_path: str, gcs_path: str) -> str:
    """Uploads a local file to the project GCS bucket. (Warning: May trigger SSL issues)"""
    from .app_utils.gcs_utils import upload_to_gcs

    try:
        uri = upload_to_gcs(local_path, gcs_path)
        return f"Successfully uploaded {local_path} to {uri}"
    except Exception as e:
        return f"Error uploading file to GCS: {e}"


def transform_infrastructure_data() -> str:
    """Deprecated: Use process_uploaded_infrastructure_file instead."""
    return "Error: This tool is deprecated. Please upload your file to the chat."
