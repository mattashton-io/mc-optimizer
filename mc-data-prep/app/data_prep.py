import os
import re
import numpy as np
import pandas as pd

def transform_infrastructure_data() -> str:
    """Transforms raw infrastructure exports from VMware and Hyper-V into Migration Center compliant CSV formats.
    
    It reads data from 'data/exports' and templates from 'data/templates',
    and generates 'vmInfo.csv' and 'diskInfo.csv' in 'data/output'.
    
    Returns:
        A string indicating success or failure.
    """
    base_dir = os.path.join(os.path.dirname(__file__), "data")
    EXPORTS_DIR = os.path.join(base_dir, "exports")
    TEMPLATES_DIR = os.path.join(base_dir, "templates")
    OUTPUT_DIR = os.path.join(base_dir, "output")

    # Ensure output dir exists
    os.makedirs(OUTPUT_DIR, exist_ok=True)

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
        # Try to extract folder name first (between ']' and '/')
        match = re.search(r"\]\s*([^/]+)/", path)
        if match:
            name = match.group(1).strip()
        else:
            # Fallback to filename without extension
            match = re.search(r"([^/]+)\.(vmx|vmdk)$", path)
            if match:
                name = match.group(1)
                # Strip common suffixes like _1, _2 from disks
                name = re.sub(r'_\d+$', '', name)
            else:
                name = "unknown-vm"
        
        # Clean name to only allow alphanumeric, underscores, and hyphens
        name = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
        return name

    def process_vmware():
        vinfo_path = os.path.join(EXPORTS_DIR, "vmware-exports", "RVTools_export_gcp.xlsx - vInfo.csv")
        vdisk_path = os.path.join(EXPORTS_DIR, "vmware-exports", "RVTools_export_gcp.xlsx - vDisk.csv")

        if not os.path.exists(vinfo_path) or not os.path.exists(vdisk_path):
            return pd.DataFrame(), pd.DataFrame()

        df_info = pd.read_csv(vinfo_path)
        df_disk = pd.read_csv(vdisk_path)

        df_info["MachineName"] = df_info["Path"].apply(extract_vm_name)
        df_disk["Path_Name"] = df_disk["Path"].apply(extract_vm_name)
        df_disk["MachineId"] = df_disk["Path_Name"]
        df_info["MachineId"] = df_info["MachineName"]

        df_disk["CapacityMiB"] = df_disk["Capacity MiB"].apply(clean_number)
        df_disk["SizeInGib"] = df_disk["CapacityMiB"] / 1024.0

        disk_sum = df_disk.groupby("MachineId")["SizeInGib"].sum().reset_index()
        disk_sum.rename(columns={"SizeInGib": "TotalDiskAllocatedGiB"}, inplace=True)

        df_info["MemoryMiB"] = df_info["Memory"].apply(clean_number)
        df_info["MemoryGiB"] = df_info["MemoryMiB"] / 1024.0
        df_info["AllocatedProcessorCoreCount"] = df_info["CPUs"]
        df_info["OsName"] = df_info["OS according to the configuration file"]

        df_vm = pd.merge(df_info, disk_sum, on="MachineId", how="left")

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
            return 'Linux' # Default fallback

        vm_info["OsName"] = df_vm["OsName"]
        vm_info["OsType(optional)"] = df_vm["OsName"].apply(map_os_type)
        vm_info["IsPhysical"] = "FALSE"
        vm_info["MachineTypeLabel(optional)"] = "VMware VM"

        disk_info = pd.DataFrame()
        disk_info["MachineId"] = df_disk["MachineId"]
        disk_info["DiskLabel"] = df_disk["Disk"]
        disk_info["SizeInGib"] = df_disk["SizeInGib"]
        disk_info["UsedInGib"] = 0
        disk_info["StorageTypeLabel"] = df_disk["Label"]

        return vm_info, disk_info

    def process_hyperv():
        hv_path = os.path.join(EXPORTS_DIR, "hyperv-exports", "hvvmInfogcp.csv")
        if not os.path.exists(hv_path):
            return pd.DataFrame(), pd.DataFrame()

        df = pd.read_csv(hv_path)

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
            return 'Linux' # Default fallback
            
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

        vms = pd.concat([vm_vmware, vm_hyperv], ignore_index=True)
        disks = pd.concat([disk_vmware, disk_hyperv], ignore_index=True)

        # Generate tags
        tags_vmware = pd.DataFrame()
        tags_vmware["MachineId"] = vm_vmware["MachineId"]
        tags_vmware["Key"] = "source"
        tags_vmware["Value"] = "vmware"

        tags_hyperv = pd.DataFrame()
        tags_hyperv["MachineId"] = vm_hyperv["MachineId"]
        tags_hyperv["Key"] = "source"
        tags_hyperv["Value"] = "hyperv"

        tags = pd.concat([tags_vmware, tags_hyperv], ignore_index=True)



        vm_template = pd.read_csv(os.path.join(TEMPLATES_DIR, "vmInfo.csv"), nrows=0)
        disk_template = pd.read_csv(os.path.join(TEMPLATES_DIR, "diskInfo.csv"), nrows=0)

        vms_final = pd.DataFrame(columns=vm_template.columns)
        for col in vms.columns:
            if col in vms_final.columns:
                vms_final[col] = vms[col]
        
        # Fill numeric columns with 0 if NaN to ensure MC validation passes
        numeric_cols = [
            "TotalDiskAllocatedGiB", "TotalDiskUsedGiB", 
            "AllocatedProcessorCoreCount", "MemoryGiB"
        ]
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

        vms_final.to_csv(os.path.join(OUTPUT_DIR, "vmInfo.csv"), index=False)
        disks_final.to_csv(os.path.join(OUTPUT_DIR, "diskInfo.csv"), index=False)
        tags.to_csv(os.path.join(OUTPUT_DIR, "tagInfo.csv"), index=False)


        return f"Successfully generated files in {OUTPUT_DIR}"
    except Exception as e:
        return f"Failed to transform data: {str(e)}"


def add_labels_to_tag_file(machine_ids: list[str], key: str, value: str) -> str:
    """Adds or updates a label (key-value pair) for a list of machine IDs in the output tagInfo.csv.
    It ensures the structure matches the template tagInfo.csv exactly (MachineId,Key,Value).
    
    Args:
        machine_ids: A list of machine IDs to label.
        key: The label key.
        value: The label value.
        
    Returns:
        A string indicating success or failure.
    """
    base_dir = os.path.join(os.path.dirname(__file__), "data")
    template_path = os.path.join(base_dir, "templates", "tagInfo.csv")
    output_path = os.path.join(base_dir, "output", "tagInfo.csv")

    if not os.path.exists(template_path):
        return f"Error: Template file {template_path} not found."

    try:
        # 1. Check template structure & get expected headers
        template_df = pd.read_csv(template_path, nrows=0)
        expected_headers = list(template_df.columns)
    except Exception as e:
        return f"Error: Failed to read template file: {e}"

    # 2. Load existing tags or start new ones
    if os.path.exists(output_path):
        try:
            tags_df = pd.read_csv(output_path)
        except Exception as e:
            return f"Error: Failed to read existing tagInfo.csv: {e}"
    else:
        tags_df = pd.DataFrame(columns=expected_headers)

    # 3. Process and add new rows
    new_rows = []
    for mid in machine_ids:
        # Ensure we clear out any existing matching key/value pairs for this machine ID to avoid duplicates
        if not tags_df.empty:
            tags_df = tags_df[~((tags_df["MachineId"] == mid) & (tags_df["Key"] == key))]
            
        new_rows.append({
            "MachineId": mid,
            "Key": key,
            "Value": value
        })

    if new_rows:
        new_df = pd.DataFrame(new_rows)
        # Align headers exactly with template
        new_df = new_df[expected_headers]
        tags_df = pd.concat([tags_df, new_df], ignore_index=True)

    # 4. Write back to file
    try:
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        tags_df.to_csv(output_path, index=False)
        return f"Successfully added/updated label '{key}={value}' for {len(machine_ids)} servers in {output_path}."
    except Exception as e:
        return f"Error: Failed to save tagInfo.csv: {e}"


def get_parsed_vms() -> str:
    """Retrieves the list of parsed VMs from the generated vmInfo.csv.
    This contains VM IDs, names, OS types, and machine types to help map VMs to MachineIds.
    
    Returns:
        A CSV-formatted string or error message.
    """
    vm_path = os.path.join(os.path.dirname(__file__), "data", "output", "vmInfo.csv")

    if not os.path.exists(vm_path):
        return "Error: No parsed VMs found in data/output/vmInfo.csv. Please run transform_infrastructure_data first."

    try:
        df = pd.read_csv(vm_path)
        cols = ["MachineId", "MachineName", "OsType(optional)", "MachineTypeLabel(optional)"]
        cols = [c for c in cols if c in df.columns]
        return df[cols].to_csv(index=False)
    except Exception as e:
        return f"Error: Failed to read VM list: {e}"
