import io
import re

import numpy as np
import pandas as pd
from google.adk.tools import ToolContext
from google.genai import types


def process_inventory_upload(file_dict: dict[str, pd.DataFrame]) -> pd.DataFrame:
    # Standardize column headers by stripping whitespace
    for sheet in file_dict:
        file_dict[sheet].columns = file_dict[sheet].columns.str.strip()

    # 1. Detect Standard Migration Center CSV
    if len(file_dict) == 1:
        df_single = next(iter(file_dict.values()))
        if (
            "AllocatedProcessorCoreCount" in df_single.columns
            and "MemoryGiB" in df_single.columns
        ):
            return df_single

    # 2. Detect RVTools Format
    expected_rvtools_sheets = ["vInfo", "vCPU", "vMemory", "vPartition"]
    is_rvtools = all(sheet in file_dict for sheet in expected_rvtools_sheets)

    if is_rvtools:
        df_vinfo = file_dict["vInfo"].copy()
        df_vmem = file_dict["vMemory"].copy()
        df_vpart = file_dict["vPartition"].copy()

        # Strip trailing/leading spaces from VM names to ensure robust merging
        if "VM" in df_vinfo.columns:
            df_vinfo["VM"] = df_vinfo["VM"].astype(str).str.strip()
        if "VM" in df_vmem.columns:
            df_vmem["VM"] = df_vmem["VM"].astype(str).str.strip()
        if "VM" in df_vpart.columns:
            df_vpart["VM"] = df_vpart["VM"].astype(str).str.strip()

        vmem_data = (
            df_vmem[["VM", "Size MiB"]].drop_duplicates(subset=["VM"])
            if "Size MiB" in df_vmem.columns
            else pd.DataFrame()
        )

        if "Capacity MiB" in df_vpart.columns and "Consumed MiB" in df_vpart.columns:
            vpart_agg = (
                df_vpart.groupby("VM")
                .agg({"Capacity MiB": "sum", "Consumed MiB": "sum"})
                .reset_index()
            )
        else:
            vpart_agg = pd.DataFrame()

        # Rename Size MiB in sheet data before merging to prevent conflict with vInfo's own columns
        if not vmem_data.empty:
            vmem_data = vmem_data.rename(columns={"Size MiB": "vmem_SizeMiB"})

        master_df = df_vinfo.copy()

        if not vmem_data.empty:
            master_df = master_df.merge(vmem_data, on="VM", how="left")
        if not vpart_agg.empty:
            master_df = master_df.merge(vpart_agg, on="VM", how="left")

        # Fallback for Size MiB: use 'vmem_SizeMiB' if present and not NaN, else fall back to 'Memory' from vInfo
        if "vmem_SizeMiB" in master_df.columns:
            master_df["Size MiB"] = master_df["vmem_SizeMiB"].fillna(
                master_df.get("Memory", 0)
            )
            master_df = master_df.drop(columns=["vmem_SizeMiB"])
        elif "Memory" in master_df.columns:
            master_df["Size MiB"] = master_df["Memory"]

        # Fallback for Capacity MiB / Consumed MiB if vPartition had no data
        if "Capacity MiB" not in master_df.columns:
            master_df["Capacity MiB"] = 0.0
            master_df["Consumed MiB"] = 0.0

        if "Total disk capacity MiB" in master_df.columns:
            zero_mask = (master_df["Capacity MiB"] == 0) | master_df[
                "Capacity MiB"
            ].isna()
            master_df.loc[zero_mask, "Capacity MiB"] = master_df.loc[
                zero_mask, "Total disk capacity MiB"
            ]

            # Fallback for Consumed MiB using In Use MiB
            if "In Use MiB" in master_df.columns:

                def clean_val(val):
                    if pd.isna(val):
                        return 0.0
                    if isinstance(val, str):
                        val = val.replace(",", "").replace('"', "")
                        try:
                            return float(val)
                        except ValueError:
                            return 0.0
                    return float(val)

                in_use_mib = master_df["In Use MiB"].apply(clean_val).fillna(0)
                master_df.loc[zero_mask, "Consumed MiB"] = in_use_mib.loc[zero_mask]

        master_df["Capacity MiB"] = master_df["Capacity MiB"].fillna(0)
        master_df["Consumed MiB"] = master_df["Consumed MiB"].fillna(0)

        return master_df

    # 3. Fallback
    return next(iter(file_dict.values()))


async def process_uploaded_infrastructure_file(
    artifact_id: str, format_type: str, tool_context: ToolContext
) -> str:
    """Processes an infrastructure export file in memory and saves it as session artifacts.

    Args:
        artifact_id: The ID (filename) of the artifact in the ADK chat.
        format_type: The source format ('vmware', 'hyperv', 'nutanix', 'proxmox', or others).

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

        # Check for raw RVTools .xlsx file pass-through
        if artifact_id.lower().endswith(".xlsx"):
            print(
                "Notice: Detected a raw RVTools (.xlsx) file. Google Cloud Migration Center natively supports this format. Staging raw 'rvtools.xlsx' artifact for direct upload..."
            )
            # Save the raw bytes directly as 'rvtools.xlsx' artifact for direct upload
            await tool_context.save_artifact("rvtools.xlsx", part)

        # Detect structure
        is_generic_template = False
        is_tag_info = False
        if artifact_id.lower().endswith(".csv"):
            with io.BytesIO(file_bytes) as f:
                header_line = f.readline().decode("utf-8").lower()
                if "machineid" in header_line and "machinename" in header_line:
                    is_generic_template = True
                elif (
                    "machineid" in header_line
                    and "key" in header_line
                    and "value" in header_line
                ):
                    is_tag_info = True

        # Handle tagInfo.csv specially
        if is_tag_info:
            with io.BytesIO(file_bytes) as f:
                df_tags = pd.read_csv(f)

            required_cols = ["MachineId", "Key", "Value"]
            if not all(col in df_tags.columns for col in required_cols):
                return "Error: Uploaded tagInfo.csv is missing required columns (MachineId, Key, Value)."

            def validate_tag(row):
                key = str(row["Key"])
                val = str(row["Value"])
                if not re.match(r"^[a-z][a-z0-9_-]{0,62}$", key.lower()):
                    return False
                if not re.match(r"^[a-z0-9_-]{0,63}$", val.lower()):
                    return False
                return True

            df_tags["valid"] = df_tags.apply(validate_tag, axis=1)
            if not df_tags["valid"].all():
                invalid = df_tags[~df_tags["valid"]]
                return f"Error: tagInfo.csv contains invalid tags. Examples: {invalid[['Key', 'Value']].head(2).to_dict()}"

            csv_content = df_tags[required_cols].to_csv(index=False)
            await tool_context.save_artifact(
                "tagInfo.csv", types.Part(text=csv_content)
            )
            await tool_context.save_artifact(
                "staged_labels.csv", types.Part(text=csv_content)
            )
            return "Successfully validated and saved tagInfo.csv/staged_labels.csv as session artifacts."

        # Load sheets or CSV
        file_dict = {}
        if artifact_id.lower().endswith(".xlsx"):
            with io.BytesIO(file_bytes) as f:
                try:
                    file_dict = pd.read_excel(f, sheet_name=None)
                except Exception as e:
                    return f"Error reading Excel file: {e}"
        else:
            with io.BytesIO(file_bytes) as f:
                try:
                    file_dict = {"default": pd.read_csv(f)}
                except Exception as e:
                    return f"Error reading CSV file: {e}"

        # Standardize column headers by stripping whitespace
        for sheet in file_dict:
            file_dict[sheet].columns = file_dict[sheet].columns.str.strip()

        # 1. Detect Standard Migration Center CSV
        is_standard_mc = False
        if len(file_dict) == 1:
            df_single = next(iter(file_dict.values()))
            if "vCPU" in df_single.columns and "Memory (MiB)" in df_single.columns:
                is_standard_mc = True

        # 2. Detect RVTools Format
        expected_rvtools_sheets = ["vInfo", "vCPU", "vMemory", "vPartition"]
        is_rvtools = all(sheet in file_dict for sheet in expected_rvtools_sheets)

        if is_standard_mc:
            df_single = next(iter(file_dict.values()))
            await tool_context.save_artifact(
                "vmInfo.csv", types.Part(text=df_single.to_csv(index=False))
            )
            # Create basic staged_labels.csv from Standard MC CSV
            tags = pd.DataFrame(columns=["MachineId", "Key", "Value"])
            m_col = (
                "MachineId"
                if "MachineId" in df_single.columns
                else (
                    "VM"
                    if "VM" in df_single.columns
                    else ("MachineName" if "MachineName" in df_single.columns else None)
                )
            )
            if m_col:
                tags["MachineId"] = df_single[m_col]
            else:
                tags["MachineId"] = [f"vm-{i}" for i in range(1, len(df_single) + 1)]
            tags["Key"] = "source_platform"
            tags["Value"] = format_type.lower()
            await tool_context.save_artifact(
                "staged_labels.csv", types.Part(text=tags.to_csv(index=False))
            )
            return (
                f"Successfully processed {len(df_single)} VMs from Standard MC CSV. "
                f"Transformed files (vmInfo.csv) have been saved as session artifacts. "
                f"You can now run 'get_parsed_vms' to review or 'import_data_to_migration_center' to proceed."
            )

        df_info = pd.DataFrame()
        df_disk = pd.DataFrame()

        if is_rvtools:
            df_info = process_inventory_upload(file_dict)
            df_disk = pd.DataFrame()
        else:
            # Fallback / original non-RVTools parsing logic
            if format_type.lower() == "vmware":
                if "vInfo" in file_dict:
                    df_info = file_dict["vInfo"]
                    df_disk = file_dict.get("vDisk", pd.DataFrame())
                else:
                    df_info = next(iter(file_dict.values()))
                    df_disk = pd.DataFrame()
            else:
                df_info = next(iter(file_dict.values()))
                df_disk = pd.DataFrame()

        if df_info.empty:
            return (
                "Error: The uploaded file appears to be empty or could not be parsed."
            )

        # Perform transformation logic
        transformed = _transform_in_memory(
            df_info, df_disk, format_type.lower(), is_generic_template
        )

        # Save as artifacts
        await tool_context.save_artifact(
            "vmInfo.csv", types.Part(text=transformed["vms"].to_csv(index=False))
        )
        if not transformed["disks"].empty:
            await tool_context.save_artifact(
                "diskInfo.csv",
                types.Part(text=transformed["disks"].to_csv(index=False)),
            )

        # Save generated tags to staged_labels.csv for API labeling
        await tool_context.save_artifact(
            "staged_labels.csv",
            types.Part(text=transformed["tags"].to_csv(index=False)),
        )

        success_msg = (
            f"Successfully processed {len(transformed['vms'])} VMs from {format_type}. "
            f"Transformed files (vmInfo.csv) have been saved as session artifacts. "
        )
        if artifact_id.lower().endswith(".xlsx"):
            success_msg += "Notice: Detected a raw RVTools (.xlsx) file. Staged raw 'rvtools.xlsx' artifact successfully for native Google Cloud Migration Center import. "
        success_msg += "You can now run 'get_parsed_vms' to review or 'import_data_to_migration_center' to proceed."

        return success_msg

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
        return df.to_csv(index=False)
    except Exception as e:
        return f"Error retrieving parsed VMs: {e}"


async def add_labels_to_staged_artifact(
    machine_ids: list[str], key: str, value: str, tool_context: ToolContext
) -> str:
    """Adds or updates a label for a list of machine IDs in the 'staged_labels.csv' session artifact."""
    try:
        part = await tool_context.load_artifact("staged_labels.csv")
        if not part:
            tags_df = pd.DataFrame(columns=["MachineId", "Key", "Value"])
        else:
            content = part.text or part.inline_data.data.decode("utf-8")
            tags_df = pd.read_csv(io.StringIO(content))

        new_rows = []
        for mid in machine_ids:
            # Deduplicate by MachineId and Key
            tags_df = tags_df[
                ~((tags_df["MachineId"] == mid) & (tags_df["Key"] == key))
            ]
            new_rows.append({"MachineId": mid, "Key": key, "Value": value})

        if new_rows:
            tags_df = pd.concat([tags_df, pd.DataFrame(new_rows)], ignore_index=True)

        await tool_context.save_artifact(
            "staged_labels.csv", types.Part(text=tags_df.to_csv(index=False))
        )
        return f"Successfully updated label '{key}={value}' for {len(machine_ids)} servers in session artifacts."
    except Exception as e:
        return f"Error updating staged labels: {e}"


def _transform_in_memory(
    df_info: pd.DataFrame,
    df_disk: pd.DataFrame,
    source_type: str,
    is_generic: bool = False,
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

    if is_generic:
        vm_info = df_info.copy()
        if "OsName" in vm_info.columns and "OsType(optional)" not in vm_info.columns:
            vm_info["OsType(optional)"] = vm_info["OsName"].apply(map_os_type)
        if "MachineTypeLabel(optional)" not in vm_info.columns:
            vm_info["MachineTypeLabel(optional)"] = f"{source_type.title()} VM"
        disk_info = df_disk.copy()

    elif source_type == "vmware":
        # Extract MachineId
        if "VM UUID" in df_info.columns:
            df_info["MachineId"] = df_info["VM UUID"].astype(str).str.strip()
        elif "VI SDK UUID" in df_info.columns:
            df_info["MachineId"] = df_info["VI SDK UUID"].astype(str).str.strip()
        else:
            df_info["MachineId"] = df_info["VM"].astype(str).str.strip()

        # MachineName
        df_info["MachineName"] = df_info["VM"].astype(str).str.strip()

        # PrimaryIPAddress
        df_info["PrimaryIPAddress(optional)"] = (
            df_info["Primary IP Address"]
            if "Primary IP Address" in df_info.columns
            else (
                df_info["PrimaryIPAddress(optional)"]
                if "PrimaryIPAddress(optional)" in df_info.columns
                else ""
            )
        )

        # OsName
        df_info["OsName"] = (
            df_info["OS according to the VMware Tools"]
            if "OS according to the VMware Tools" in df_info.columns
            else (
                df_info["OS according to the configuration file"]
                if "OS according to the configuration file" in df_info.columns
                else df_info.get("OsName", "Linux")
            )
        )

        # MachineStatus
        def map_machine_status(power_state):
            if pd.isna(power_state):
                return "user stopped"
            state = str(power_state).strip().lower()
            if state == "poweredon":
                return "running"
            if state == "poweredoff":
                return "user stopped"
            return "user stopped"

        df_info["MachineStatus(optional)"] = (
            df_info["Powerstate"].apply(map_machine_status)
            if "Powerstate" in df_info.columns
            else "running"
        )

        # MemoryGiB
        if "Size MiB" in df_info.columns:
            df_info["MemoryGiB"] = df_info["Size MiB"].apply(clean_number) / 1024.0
        elif "Memory" in df_info.columns:
            df_info["MemoryGiB"] = df_info["Memory"].apply(clean_number) / 1024.0
        else:
            df_info["MemoryGiB"] = 0.0

        # AllocatedProcessorCoreCount
        if "CPUs" in df_info.columns:
            df_info["AllocatedProcessorCoreCount"] = (
                df_info["CPUs"].apply(clean_number).fillna(0).astype(int)
            )
        else:
            df_info["AllocatedProcessorCoreCount"] = 0

        # TotalDiskAllocatedGiB and TotalDiskUsedGiB
        if "Capacity MiB" in df_info.columns:
            df_info["TotalDiskAllocatedGiB"] = (
                df_info["Capacity MiB"].apply(clean_number) / 1024.0
            )
            if "Consumed MiB" in df_info.columns:
                df_info["TotalDiskUsedGiB"] = (
                    df_info["Consumed MiB"].apply(clean_number) / 1024.0
                )
            else:
                df_info["TotalDiskUsedGiB"] = df_info["TotalDiskAllocatedGiB"]
            df_vm = df_info.copy()
        elif not df_disk.empty:
            df_disk["Path_Name"] = (
                df_disk["Path"].apply(extract_vm_name)
                if "Path" in df_disk.columns
                else df_disk["VM"]
            )
            df_disk["MachineId"] = df_disk["Path_Name"]
            df_disk["CapacityMiB"] = df_disk["Capacity MiB"].apply(clean_number)
            disk_sum = df_disk.groupby("MachineId")["CapacityMiB"].sum().reset_index()
            disk_sum.rename(columns={"CapacityMiB": "CapacityMiB_Sum"}, inplace=True)
            df_vm = pd.merge(df_info, disk_sum, on="MachineId", how="left")
            df_vm["TotalDiskAllocatedGiB"] = df_vm["CapacityMiB_Sum"].fillna(0) / 1024.0
            df_vm["TotalDiskUsedGiB"] = df_vm["TotalDiskAllocatedGiB"]

            disk_info["MachineId"] = df_disk["MachineId"]
            disk_info["DiskLabel"] = df_disk.get("Disk", "disk-0")
            disk_info["SizeInGib"] = df_disk["CapacityMiB"] / 1024.0
            disk_info["UsedInGib"] = 0
            disk_info["StorageTypeLabel"] = df_disk.get("Label", "VMware")
        else:
            df_vm = df_info.copy()
            df_vm["TotalDiskAllocatedGiB"] = 0.0
            df_vm["TotalDiskUsedGiB"] = 0.0

        vm_info["MachineId"] = df_vm["MachineId"]
        vm_info["MachineName"] = df_vm["MachineName"]
        vm_info["PrimaryIPAddress(optional)"] = df_vm["PrimaryIPAddress(optional)"]
        vm_info["TotalDiskAllocatedGiB"] = df_vm["TotalDiskAllocatedGiB"]
        vm_info["TotalDiskUsedGiB"] = df_vm["TotalDiskUsedGiB"]
        vm_info["AllocatedProcessorCoreCount"] = df_vm["AllocatedProcessorCoreCount"]
        vm_info["MemoryGiB"] = df_vm["MemoryGiB"]
        vm_info["OsName"] = df_vm["OsName"]
        vm_info["OsType(optional)"] = df_vm["OsName"].apply(map_os_type)
        vm_info["MachineStatus(optional)"] = df_vm["MachineStatus(optional)"]
        vm_info["IsPhysical"] = "FALSE"
        vm_info["MachineTypeLabel(optional)"] = "VMware VM"

    elif source_type == "hyperv":
        df_info["MachineId"] = [f"hv-vm-{i}" for i in range(1, len(df_info) + 1)]
        df_info["MachineName"] = df_info["MachineId"]

        vm_info["MachineId"] = df_info["MachineId"]
        vm_info["MachineName"] = df_info["MachineName"]
        vm_info["PrimaryIPAddress(optional)"] = ""
        vm_info["TotalDiskAllocatedGiB"] = df_info["TotalDiskAllocatedGiB"]
        vm_info["TotalDiskUsedGiB"] = df_info["TotalDiskUsedGiB"]
        vm_info["AllocatedProcessorCoreCount"] = df_info["AllocatedProcessorCoreCount"]
        vm_info["MemoryGiB"] = df_info["MemoryGiB"]
        vm_info["OsName"] = df_info["OsName"]
        vm_info["OsType(optional)"] = df_info["OsName"].apply(map_os_type)
        vm_info["MachineStatus(optional)"] = "running"
        vm_info["IsPhysical"] = "FALSE"
        vm_info["MachineTypeLabel(optional)"] = "Hyper-V VM"

        disk_info["MachineId"] = df_info["MachineId"]
        disk_info["DiskLabel"] = "disk-0"
        disk_info["SizeInGib"] = df_info["TotalDiskAllocatedGiB"]
        disk_info["UsedInGib"] = df_info["TotalDiskUsedGiB"]
        disk_info["StorageTypeLabel"] = "Hyper-V"

    tags = pd.DataFrame(columns=["MachineId", "Key", "Value"])
    tags["MachineId"] = vm_info["MachineId"]
    # Use underscore consistently to avoid duplicate-like behavior with source-platform
    tags["Key"] = "source_platform"
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
