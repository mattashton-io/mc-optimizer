import pandas as pd
import os
import uuid
import re
from typing import Dict, List

def clean_numeric(val):
    """Safely converts string with commas/quotes to float."""
    if pd.isna(val) or val == '':
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    # Remove commas, quotes, and any non-numeric chars except decimal point
    cleaned = re.sub(r'[^\d.]', '', str(val))
    try:
        return float(cleaned)
    except ValueError:
        return 0.0

def normalize_os(os_string):
    """Maps varied OS names to Migration Center compliant values."""
    os_string = str(os_string).lower()
    if 'windows' in os_string:
        return 'Windows'
    if any(x in os_string for x in ['linux', 'ubuntu', 'rhel', 'centos', 'debian', 'suse', 'freebsd']):
        return 'Linux'
    return 'Linux' # Default to Linux for compatibility if unknown

def get_vm_name_from_path(path):
    """Extracts VM name from VMware path like [ds] folder/vm.vmx"""
    if pd.isna(path):
        return "Unknown-VM"
    # Match the part between ] and / or just the file name
    match = re.search(r'\]\s*([^/]+)/', str(path))
    if match:
        return match.group(1).strip()
    return os.path.basename(str(path)).replace('.vmx', '')

class MigrationCenterTransformer:
    def __init__(self):
        self.vm_name_to_id = {}

    def transform_vmware(self, vinfo_path: str, vdisk_path: str) -> Dict[str, pd.DataFrame]:
        """Transforms RVTools vInfo and vDisk to MC format."""
        vinfo_df = pd.read_csv(vinfo_path)
        vdisk_df = pd.read_csv(vdisk_path)

        # 1. Process vInfo (VMs)
        vm_records = []
        for _, row in vinfo_df.iterrows():
            vm_name = get_vm_name_from_path(row.get('Path', ''))
            # Generate deterministic UUID for consistency
            m_id = f"iona-uuid-{uuid.uuid5(uuid.NAMESPACE_DNS, vm_name).hex[:8]}"
            self.vm_name_to_id[vm_name] = m_id

            vm_records.append({
                'MachineId': m_id,
                'MachineName': vm_name,
                'AllocatedProcessorCoreCount': clean_numeric(row.get('CPUs', 0)),
                'MemoryGiB': clean_numeric(row.get('Memory', 0)) / 1024.0, # MiB to GiB
                'TotalDiskAllocatedGiB': clean_numeric(row.get('Total disk capacity MiB', 0)) / 1024.0,
                'OsType': normalize_os(row.get('OS according to the configuration file', '')),
                'OsName': row.get('OS according to the configuration file', ''),
                'IsPhysical': 0
            })
        
        vminfo_out = pd.DataFrame(vm_records)

        # 2. Process vDisk (Disks)
        disk_records = []
        for _, row in vdisk_df.iterrows():
            vm_name = get_vm_name_from_path(row.get('Path', ''))
            m_id = self.vm_name_to_id.get(vm_name)
            if not m_id:
                continue # Skip disks for VMs not in vInfo

            disk_records.append({
                'MachineId': m_id,
                'DiskLabel': row.get('Disk', 'Hard disk'),
                'SizeInGib': clean_numeric(row.get('Capacity MiB', 0)) / 1024.0,
                'StorageTypeLabel': 'Persistent'
            })
        
        diskinfo_out = pd.DataFrame(disk_records)

        return {
            'vminfo': vinfo_out,
            'diskinfo': diskinfo_out
        }

    def transform_hyperv(self, hv_path: str) -> pd.DataFrame:
        """Transforms Hyper-V hvvmInfogcp.csv to MC format."""
        df = pd.read_csv(hv_path)
        vm_records = []
        for i, row in df.iterrows():
            vm_name = f"hv-vm-{i+1}"
            m_id = f"iona-uuid-hv-{i+1}"
            
            vm_records.append({
                'MachineId': m_id,
                'MachineName': vm_name,
                'AllocatedProcessorCoreCount': clean_numeric(row.get('AllocatedProcessorCoreCount', 0)),
                'MemoryGiB': clean_numeric(row.get('MemoryGiB', 0)),
                'TotalDiskAllocatedGiB': clean_numeric(row.get('TotalDiskAllocatedGiB', 0)),
                'OsType': normalize_os(row.get('OsType', '')),
                'OsName': row.get('OsName', ''),
                'IsPhysical': 0
            })
        return pd.DataFrame(vm_records)

def run_transformation(exports_dir: str, output_dir: str):
    """Main entry point for the transformation process."""
    transformer = MigrationCenterTransformer()
    os.makedirs(output_dir, exist_ok=True)

    all_vminfo = []
    all_diskinfo = []

    # VMware processing
    vmware_dir = os.path.join(exports_dir, 'vmware-exports')
    if os.path.exists(vmware_dir):
        vinfo_files = [f for f in os.listdir(vmware_dir) if 'vInfo' in f]
        vdisk_files = [f for f in os.listdir(vmware_dir) if 'vDisk' in f]
        
        if vinfo_files and vdisk_files:
            res = transformer.transform_vmware(
                os.path.join(vmware_dir, vinfo_files[0]),
                os.path.join(vmware_dir, vdisk_files[0])
            )
            all_vminfo.append(res['vminfo'])
            all_diskinfo.append(res['diskinfo'])

    # Hyper-V processing
    hyperv_path = os.path.join(exports_dir, 'hyperv-exports', 'hvvmInfogcp.csv')
    if os.path.exists(hyperv_path):
        all_vminfo.append(transformer.transform_hyperv(hyperv_path))

    if all_vminfo:
        pd.concat(all_vminfo).to_csv(os.path.join(output_dir, 'vminfo.csv'), index=False)
    if all_diskinfo:
        pd.concat(all_diskinfo).to_csv(os.path.join(output_dir, 'diskinfo.csv'), index=False)
    
    return f"Transformation complete. Files saved to {output_dir}"

if __name__ == "__main__":
    # Example usage
    print(run_transformation('mc-data-prep/data/exports', 'mc-data-prep/data/output'))
