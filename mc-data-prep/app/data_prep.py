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
        match = re.search(r"([^/]+)\.(vmx|vmdk)$", path)
        if match:
            return match.group(1)
        return "unknown-vm"

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
        vm_info["OsName"] = df_vm["OsName"]
        vm_info["IsPhysical"] = 0

        disk_info = pd.DataFrame()
        disk_info["MachineId"] = df_disk["MachineId"]
        disk_info["DiskLabel"] = df_disk["Disk"]
        disk_info["SizeInGib"] = df_disk["SizeInGib"]
        disk_info["UsedInGib"] = np.nan
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
        vm_info["IsPhysical"] = 0

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

        vm_template = pd.read_csv(os.path.join(TEMPLATES_DIR, "vmInfo.csv"), nrows=0)
        disk_template = pd.read_csv(os.path.join(TEMPLATES_DIR, "diskInfo.csv"), nrows=0)

        vms_final = pd.DataFrame(columns=vm_template.columns)
        for col in vms.columns:
            if col in vms_final.columns:
                vms_final[col] = vms[col]

        disks_final = pd.DataFrame(columns=disk_template.columns)
        for col in disks.columns:
            if col in disks_final.columns:
                disks_final[col] = disks[col]

        vms_final.to_csv(os.path.join(OUTPUT_DIR, "vmInfo.csv"), index=False)
        disks_final.to_csv(os.path.join(OUTPUT_DIR, "diskInfo.csv"), index=False)

        return f"Successfully generated files in {OUTPUT_DIR}"
    except Exception as e:
        return f"Failed to transform data: {str(e)}"
