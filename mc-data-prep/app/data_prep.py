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
    EXPORTS_DIR = "data/exports"
    TEMPLATES_DIR = "data/templates"
    OUTPUT_DIR = "data/output"

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
