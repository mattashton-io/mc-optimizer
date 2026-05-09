import pandas as pd
import numpy as np
import os
import re

def clean_numeric(series):
    """
    Cleans string-based numeric columns (e.g., '1,024.00') 
    and converts to float.
    """
    if series.dtype == 'object':
        # Remove commas and any other non-numeric chars except the decimal point
        series = series.str.replace(r'[^-0-9.]', '', regex=True)
    return pd.to_numeric(series, errors='coerce').fillna(0)

def transform_rvtools():
    # File definitions based on uploaded RVTools parts
    vinfo_file = 'RVTools_export_gcp.xlsx - vInfo.csv'
    
    if not os.path.exists(vinfo_file):
        print(f"Error: {vinfo_file} not found.")
        return

    # Load Source Data
    # Adding low_memory=False to handle mixed types in large exports
    df_vinfo = pd.read_csv(vinfo_file, low_memory=False)
    
    # --- DATA CLEANING STEP (Resolves the TypeError) ---
    # Ensure memory and disk columns are treated as floats
    df_vinfo['Total disk capacity MiB'] = clean_numeric(df_vinfo['Total disk capacity MiB'])
    df_vinfo['Memory'] = clean_numeric(df_vinfo['Memory'])
    df_vinfo['CPUs'] = clean_numeric(df_vinfo['CPUs'])
    # Provisioned MiB often acts as a proxy for 'Allocated' if Total disk is unavailable
    if 'Provisioned MiB' in df_vinfo.columns:
        df_vinfo['Provisioned MiB'] = clean_numeric(df_vinfo['Provisioned MiB'])
    
    # 1. Generate Synthetic Identifiers
    # Row-based indexing ensures we don't need the removed UUIDs
    df_vinfo['MachineId'] = [f"iona-vmw-uuid-{i+1:04d}" for i in range(len(df_vinfo))]
    df_vinfo['MachineName'] = [f"Iona-VMW-{i+1:03d}" for i in range(len(df_vinfo))]

    # 2. Map OS Types for Migration Center compatibility
    def map_os(val):
        val = str(val).lower()
        if 'windows' in val: return 'Windows'
        if 'linux' in val or 'ubuntu' in val or 'rhel' in val or 'debian' in val: return 'Linux'
        return 'Linux' # Default fallback for table import success

    # 3. Create vminfo.csv (Asset Table)
    vminfo = pd.DataFrame()
    vminfo['MachineId'] = df_vinfo['MachineId']
    vminfo['MachineName'] = df_vinfo['MachineName']
    vminfo['PrimaryIPAddress(optional)'] = ''
    vminfo['PrimaryMACAddress(optional)'] = ''
    vminfo['PublicIPAddress(optional)'] = ''
    vminfo['IpAddressListSemiColonDelimited(optional)'] = ''
    
    # Capacity Conversion: MiB to GiB (Value / 1024)
    # The clean_numeric call above ensures these are now floats
    vminfo['TotalDiskAllocatedGiB'] = (df_vinfo['Total disk capacity MiB'] / 1024).round(2)
    
    # Use 50% as a safe 'Used' baseline if 'In Use MiB' is missing/zero
    if 'In Use MiB' in df_vinfo.columns:
        used_mib = clean_numeric(df_vinfo['In Use MiB'])
        vminfo['TotalDiskUsedGiB'] = (used_mib / 1024).round(2)
    else:
        vminfo['TotalDiskUsedGiB'] = (vminfo['TotalDiskAllocatedGiB'] * 0.5).round(2)
    
    vminfo['MachineTypeLabel(optional)'] = 'VMware VM'
    vminfo['AllocatedProcessorCoreCount'] = df_vinfo['CPUs'].astype(int)
    vminfo['MemoryGiB'] = (df_vinfo['Memory'] / 1024).round(2)
    vminfo['HostingLocation(optional)'] = 'Iona-OnPrem'
    vminfo['OsType(optional)'] = df_vinfo['OS according to the VMware Tools'].apply(map_os)
    vminfo['OsPublisher(optional)'] = ''
    vminfo['OsName'] = df_vinfo['OS according to the VMware Tools'].fillna('Other Linux')
    vminfo['OsVersion(optional)'] = ''
    vminfo['MachineStatus(optional)'] = df_vinfo['Powerstate'].map({'poweredOn': 'Running', 'poweredOff': 'Stopped'}).fillna('Running')
    vminfo['ProvisioningState(optional)'] = 'Provisioned'
    vminfo['CreateDate(optional)'] = ''
    vminfo['IsPhysical'] = 'FALSE'

    # 4. Create diskinfo.csv (Disk Table)
    diskinfo = pd.DataFrame()
    diskinfo['MachineId'] = df_vinfo['MachineId']
    diskinfo['DiskLabel'] = 'Hard disk 1'
    diskinfo['SizeInGib'] = vminfo['TotalDiskAllocatedGiB']
    diskinfo['UsedInGib'] = vminfo['TotalDiskUsedGiB']
    diskinfo['StorageTypeLabel'] = 'vmdk'

    # Final validation: Migration Center rejects imports if mandatory numeric fields are empty
    vminfo = vminfo.fillna(0)
    diskinfo = diskinfo.fillna(0)

    # Export to CSV
    vminfo.to_csv('vminfo.csv', index=False)
    diskinfo.to_csv('diskinfo.csv', index=False)
    
    print(f"Transformation Complete: Processed {len(vminfo)} VMware assets.")
    print("Files 'vminfo.csv' and 'diskinfo.csv' are ready for Table Import.")

if __name__ == "__main__":
    transform_rvtools()