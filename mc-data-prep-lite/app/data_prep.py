import os
import re

import numpy as np
import pandas as pd

from .app_utils.gcs_utils import (
    get_bucket_name,
    list_gcs_files,
    upload_to_gcs,
)


def upload_file_to_gcs(local_path: str, gcs_path: str) -> str:
    """Uploads a local file (e.g. from chat) to the project GCS bucket.
    
    Args:
        local_path: The local path of the file to upload.
        gcs_path: The destination path in GCS (e.g. 'exports/vmware-exports/vinfo.csv').
        
    Returns:
        The GCS URI of the uploaded file.
    """
    try:
        uri = upload_to_gcs(local_path, gcs_path)
        return f"Successfully uploaded {local_path} to {uri}"
    except Exception as e:
        return f"Error uploading file to GCS: {e}"

def transform_infrastructure_data() -> str:
    """Transforms raw infrastructure exports from VMware and Hyper-V in GCS into Migration Center compliant CSV formats in GCS.
    
    It reads data from 'gs://<bucket>/exports' and templates (if they exist in GCS, else local),
    and generates 'vmInfo.csv', 'diskInfo.csv', and 'tagInfo.csv' in 'gs://<bucket>/output'.
    
    Returns:
        A string indicating success or failure.
    """
    bucket_name = get_bucket_name()
    gcs_base = f"gs://{bucket_name}"
    exports_prefix = "exports/"
    output_prefix = "output/"
    template_prefix = "templates/"

    local_templates_dir = os.path.join(os.path.dirname(__file__), "data", "templates")

    def ensure_templates_in_gcs():
        for t in ["vmInfo.csv", "diskInfo.csv", "tagInfo.csv"]:
            gcs_path = f"{template_prefix}{t}"
            if not list_gcs_files(gcs_path):
                local_path = os.path.join(local_templates_dir, t)
                if os.path.exists(local_path):
                    upload_to_gcs(local_path, gcs_path)

    ensure_templates_in_gcs()

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
            name = match.group(1).strip()
        else:
            match = re.search(r"([^/]+)\.(vmx|vmdk)$", path)
            if match:
                name = match.group(1)
                name = re.sub(r'_\d+$', '', name)
            else:
                name = "unknown-vm"
        name = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
        return name

    def process_vmware():
        vinfo_gcs = f"{gcs_base}/{exports_prefix}vmware-exports/RVTools_export_gcp.xlsx - vInfo.csv"
        vdisk_gcs = f"{gcs_base}/{exports_prefix}vmware-exports/RVTools_export_gcp.xlsx - vDisk.csv"

        try:
            df_info = pd.read_csv(vinfo_gcs)
        except Exception:
            print(f"VMware vInfo file not found in GCS: {vinfo_gcs}")
            return pd.DataFrame(), pd.DataFrame()

        df_info["MachineName"] = df_info["Path"].apply(extract_vm_name)
        df_info["MachineId"] = df_info["MachineName"]
        df_info["MemoryMiB"] = df_info["Memory"].apply(clean_number)
        df_info["MemoryGiB"] = df_info["MemoryMiB"] / 1024.0
        df_info["AllocatedProcessorCoreCount"] = df_info["CPUs"]
        df_info["OsName"] = df_info["OS according to the configuration file"]

        try:
            df_disk = pd.read_csv(vdisk_gcs)
            df_disk["Path_Name"] = df_disk["Path"].apply(extract_vm_name)
            df_disk["MachineId"] = df_disk["Path_Name"]
            df_disk["CapacityMiB"] = df_disk["Capacity MiB"].apply(clean_number)
            df_disk["SizeInGib"] = df_disk["CapacityMiB"] / 1024.0
            disk_sum = df_disk.groupby("MachineId")["SizeInGib"].sum().reset_index()
            disk_sum.rename(columns={"SizeInGib": "TotalDiskAllocatedGiB"}, inplace=True)
            df_vm = pd.merge(df_info, disk_sum, on="MachineId", how="left")
            disk_info = pd.DataFrame()
            disk_info["MachineId"] = df_disk["MachineId"]
            disk_info["DiskLabel"] = df_disk["Disk"]
            disk_info["SizeInGib"] = df_disk["SizeInGib"]
            disk_info["UsedInGib"] = 0
            disk_info["StorageTypeLabel"] = df_disk["Label"]
        except Exception:
            print(f"VMware vDisk file not found in GCS: {vdisk_gcs}. Proceeding with vInfo only.")
            df_vm = df_info.copy()
            df_vm["TotalDiskAllocatedGiB"] = 0
            disk_info = pd.DataFrame()

        vm_info = pd.DataFrame()
        vm_info["MachineId"] = df_vm["MachineId"]
        vm_info["MachineName"] = df_vm["MachineName"]
        vm_info["TotalDiskAllocatedGiB"] = df_vm["TotalDiskAllocatedGiB"]
        vm_info["AllocatedProcessorCoreCount"] = df_vm["AllocatedProcessorCoreCount"]
        vm_info["MemoryGiB"] = df_vm["MemoryGiB"]

        def map_os_type(os_name):
            os_name = str(os_name).lower()
            if 'windows' in os_name: return 'Windows'
            if 'linux' in os_name or 'ubuntu' in os_name or 'rhel' in os_name or 'debian' in os_name: return 'Linux'
            return 'Linux'

        vm_info["OsName"] = df_vm["OsName"]
        vm_info["OsType(optional)"] = df_vm["OsName"].apply(map_os_type)
        vm_info["IsPhysical"] = "FALSE"
        vm_info["MachineTypeLabel(optional)"] = "VMware VM"

        return vm_info, disk_info

    def process_hyperv():
        hv_gcs = f"{gcs_base}/{exports_prefix}hyperv-exports/hvvmInfogcp.csv"
        try:
            df = pd.read_csv(hv_gcs)
        except Exception:
            print(f"Hyper-V export file not found in GCS: {hv_gcs}")
            return pd.DataFrame(), pd.DataFrame()

        if df.empty:
            return pd.DataFrame(), pd.DataFrame()

        df["MachineId"] = [f"hv-vm-{i}" for i in range(1, len(df) + 1)]
        df["MachineName"] = df["MachineId"]

        vm_info = pd.DataFrame()
        vm_info["MachineId"] = df["MachineId"]
        vm_info["MachineName"] = df["MachineName"]
        vm_info["TotalDiskAllocatedGiB"] = df["TotalDiskAllocatedGiB"]
        vm_info["TotalDiskUsedGiB"] = df["TotalDiskUsedGiB"]
        vm_info["AllocatedProcessorCoreCount"] = df["AllocatedProcessorCoreCount"]
        vm_info["MemoryGiB"] = df["MemoryGiB"]
        vm_info["OsName"] = df["OsName"]

        def map_os_type(os_name):
            os_name = str(os_name).lower()
            if 'windows' in os_name: return 'Windows'
            if 'linux' in os_name or 'ubuntu' in os_name or 'rhel' in os_name or 'debian' in os_name: return 'Linux'
            return 'Linux'

        vm_info["OsType(optional)"] = df["OsName"].apply(map_os_type)
        vm_info["IsPhysical"] = "FALSE"
        vm_info["MachineTypeLabel(optional)"] = "Hyper-V VM"

        disk_info = pd.DataFrame()
        disk_info["MachineId"] = df["MachineId"]
        disk_info["DiskLabel"] = "disk-0"
        disk_info["SizeInGib"] = df["TotalDiskAllocatedGiB"]
        disk_info["UsedInGib"] = df["TotalDiskUsedGiB"]
        disk_info["StorageTypeLabel"] = "Hyper-V"

        return vm_info, disk_info

    try:
        vm_vmware, disk_vmware = process_vmware()
        vm_hyperv, disk_hyperv = process_hyperv()

        if vm_vmware.empty and vm_hyperv.empty:
            return "Error: No data found in GCS exports. Please ensure your RVTools or Hyper-V CSV files are uploaded to GCS."

        vms = pd.concat([vm_vmware, vm_hyperv], ignore_index=True)
        disks = pd.concat([disk_vmware, disk_hyperv], ignore_index=True)

        tags_list = []
        if not vm_vmware.empty:
            tags_vmware = pd.DataFrame()
            tags_vmware["MachineId"] = vm_vmware["MachineId"]
            tags_vmware["Key"] = "source"
            tags_vmware["Value"] = "vmware"
            tags_list.append(tags_vmware)

        if not vm_hyperv.empty:
            tags_hyperv = pd.DataFrame()
            tags_hyperv["MachineId"] = vm_hyperv["MachineId"]
            tags_hyperv["Key"] = "source"
            tags_hyperv["Value"] = "hyperv"
            tags_list.append(tags_hyperv)

        tags = pd.concat(tags_list, ignore_index=True) if tags_list else pd.DataFrame(columns=["MachineId", "Key", "Value"])

        vm_template = pd.read_csv(f"{gcs_base}/{template_prefix}vmInfo.csv", nrows=0)
        disk_template = pd.read_csv(f"{gcs_base}/{template_prefix}diskInfo.csv", nrows=0)

        vms_final = pd.DataFrame(columns=vm_template.columns)
        for col in vms.columns:
            if col in vms_final.columns:
                vms_final[col] = vms[col]

        numeric_cols = ["TotalDiskAllocatedGiB", "TotalDiskUsedGiB", "AllocatedProcessorCoreCount", "MemoryGiB"]
        for col in numeric_cols:
            if col in vms_final.columns:
                vms_final[col] = pd.to_numeric(vms_final[col], errors='coerce').fillna(0)

        disks_final = pd.DataFrame(columns=disk_template.columns)
        for col in disks.columns:
            if col in disks_final.columns:
                disks_final[col] = disks[col]

        if "SizeInGib" in disks_final.columns:
            disks_final["SizeInGib"] = pd.to_numeric(disks_final["SizeInGib"], errors='coerce').fillna(0)
        if "UsedInGib" in disks_final.columns:
            disks_final["UsedInGib"] = pd.to_numeric(disks_final["UsedInGib"], errors='coerce').fillna(0)

        vms_final.to_csv(f"{gcs_base}/{output_prefix}vmInfo.csv", index=False)
        disks_final.to_csv(f"{gcs_base}/{output_prefix}diskInfo.csv", index=False)
        tags.to_csv(f"{gcs_base}/{output_prefix}tagInfo.csv", index=False)

        return f"Successfully generated files in {gcs_base}/{output_prefix}"
    except Exception as e:
        return f"Failed to transform data: {e!s}"

def add_labels_to_tag_file(machine_ids: list[str], key: str, value: str) -> str:
    """Adds or updates a label (key-value pair) for a list of machine IDs in the output tagInfo.csv in GCS."""
    bucket_name = get_bucket_name()
    gcs_base = f"gs://{bucket_name}"
    template_path = f"{gcs_base}/templates/tagInfo.csv"
    output_path = f"{gcs_base}/output/tagInfo.csv"

    try:
        template_df = pd.read_csv(template_path, nrows=0)
        expected_headers = list(template_df.columns)
    except Exception as e:
        return f"Error: Failed to read template file from GCS: {e}"

    try:
        tags_df = pd.read_csv(output_path)
    except Exception:
        tags_df = pd.DataFrame(columns=expected_headers)

    id_col = "MachineId"
    for col in expected_headers:
        if col.lower().replace(" ", "").replace("_", "") in ["machineid", "machine"]:
            id_col = col
            break
    key_col = "Key"
    for col in expected_headers:
        if col.lower().replace(" ", "").replace("_", "") in ["key", "tagcategory", "category"]:
            key_col = col
            break
    val_col = "Value"
    for col in expected_headers:
        if col.lower().replace(" ", "").replace("_", "") in ["value", "tagvalue"]:
            val_col = col
            break

    new_rows = []
    for mid in machine_ids:
        if not tags_df.empty and id_col in tags_df.columns and key_col in tags_df.columns:
            tags_df = tags_df[~((tags_df[id_col] == mid) & (tags_df[key_col] == key))]
        new_rows.append({id_col: mid, key_col: key, val_col: value})

    if new_rows:
        new_df = pd.DataFrame(new_rows)
        new_df = new_df[expected_headers]
        tags_df = pd.concat([tags_df, new_df], ignore_index=True)

    try:
        tags_df.to_csv(output_path, index=False)
        return f"Successfully added/updated label '{key}={value}' for {len(machine_ids)} servers in {output_path}."
    except Exception as e:
        return f"Error: Failed to save tagInfo.csv to GCS: {e}"

def get_parsed_vms() -> str:
    """Retrieves the list of parsed VMs from the generated vmInfo.csv in GCS."""
    bucket_name = get_bucket_name()
    vm_path = f"gs://{bucket_name}/output/vmInfo.csv"

    try:
        df = pd.read_csv(vm_path)
        cols = ["MachineId", "MachineName", "OsType(optional)", "MachineTypeLabel(optional)"]
        cols = [c for c in cols if c in df.columns]
        return df[cols].to_csv(index=False)
    except Exception:
        return f"Error: No parsed VMs found in {vm_path}. Please run transform_infrastructure_data first."
