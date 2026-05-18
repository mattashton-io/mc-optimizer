import pandas as pd
import numpy as np
import os

def transform_data():
    # Load the primary discovery files
    vm_source = 'hvvmInfogcp.csv'
    # Note: Using the user-provided hvvmInfogcp.csv for VM data 
    # and identifying if diskInfo.csv exists for granular disk data
    
    if not os.path.exists(vm_source):
        print(f"Error: {vm_source} not found.")
        return

    df_raw = pd.read_csv(vm_source)
    
    # 1. Create Naming Convention and MachineId cross-walk
    # Generating unique IDs and Names as they were missing in the raw export
    df_raw['MachineId'] = [f"iona-uuid-{i+1:04d}" for i in range(len(df_raw))]
    df_raw['MachineName'] = [f"Iona-VM-{i+1:03d}" for i in range(len(df_raw))]
    
    # 2. Prepare vminfo.csv (Asset Table)
    # Mapping logic for OsType (Normalization for Migration Center)
    def map_os_type(os_name):
        os_name = str(os_name).lower()
        if 'windows' in os_name: return 'Windows'
        if 'linux' in os_name or 'ubuntu' in os_name or 'rhel' in os_name: return 'Linux'
        return 'Linux' # Default fallback

    print((df_raw['OsName'] == "").sum())

    # Construct the vminfo dataframe with specific required headers
    vminfo = pd.DataFrame()
    vminfo['MachineId'] = df_raw['MachineId']
    vminfo['MachineName'] = df_raw['MachineName']
    vminfo['PrimaryIPAddress(optional)'] = '' 
    vminfo['PrimaryMACAddress(optional)'] = ''
    vminfo['PublicIPAddress(optional)'] = ''
    vminfo['IpAddressListSemiColonDelimited(optional)'] = ''
    vminfo['TotalDiskAllocatedGiB'] = df_raw['TotalDiskAllocatedGiB'].fillna(0)
    vminfo['TotalDiskUsedGiB'] = df_raw['TotalDiskUsedGiB'].fillna(0)
    vminfo['MachineTypeLabel(optional)'] = df_raw['MachineTypeLabel'].fillna('Virtual Machine')
    vminfo['AllocatedProcessorCoreCount'] = df_raw['AllocatedProcessorCoreCount'].fillna(1).astype(int)
    vminfo['MemoryGiB'] = df_raw['MemoryGiB'].fillna(0)
    vminfo['HostingLocation(optional)'] = 'On-Premises'
    vminfo['OsType(optional)'] = df_raw['OsName'].apply(map_os_type)
    vminfo['OsPublisher(optional)'] = ''
    vminfo['OsName'] = df_raw['OsName'].fillna('Unknown Linux')
    vminfo['OsVersion(optional)'] = df_raw['OsVersion'].fillna('')
    vminfo['MachineStatus(optional)'] = df_raw['MachineStatus'].fillna('Running')
    vminfo['ProvisioningState(optional)'] = 'Provisioned'
    vminfo['CreateDate(optional)'] = ''
    vminfo['IsPhysical'] = df_raw['IsPhysical'].map({True: 'TRUE', False: 'FALSE'}).fillna('FALSE')

    print(df_raw['OsName'].value_counts(dropna=False))
    print(vminfo['OsName'].value_counts())


    # 3. Prepare diskinfo.csv (Disk Table)
    # Mapping based on the aggregated disk info in the VM source
    diskinfo = pd.DataFrame({
        'MachineId': df_raw['MachineId'],
        'DiskLabel': 'sda1_root',
        'SizeInGib': df_raw['TotalDiskAllocatedGiB'].fillna(0),
        'UsedInGib': df_raw['TotalDiskUsedGiB'].fillna(0),
        'StorageTypeLabel': 'Standard'
    })

    # Export to files
    vminfo.to_csv('vminfo.csv', index=False)
    diskinfo.to_csv('diskinfo.csv', index=False)
    
    print("Success: vminfo.csv and diskinfo.csv generated with correct MC headers.")
    print(f"Processed {len(vminfo)} server records.")

if __name__ == "__main__":
    transform_data()