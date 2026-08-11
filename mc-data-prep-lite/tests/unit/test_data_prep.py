# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import pandas as pd

from app.data_prep import _transform_in_memory, process_inventory_upload


def test_process_inventory_upload_standard_mc_csv() -> None:
    """Tests that a standard Migration Center CSV is returned unmodified."""
    df_single = pd.DataFrame(
        {
            "VM": ["vm-1", "vm-2"],
            "AllocatedProcessorCoreCount": [2, 4],
            "MemoryGiB": [4.0, 8.0],
        }
    )
    file_dict = {"default": df_single}
    result = process_inventory_upload(file_dict)
    pd.testing.assert_frame_equal(result, df_single)


def test_process_inventory_upload_rvtools_format() -> None:
    """Tests that RVTools format sheets are correctly aggregated, joined, and fell back."""
    df_vinfo = pd.DataFrame(
        {
            "VM": ["vm-1", "vm-2"],
            "Path": ["[ds] vm-1/vm-1.vmx", "[ds] vm-2/vm-2.vmx"],
            "CPUs": [1, 2],  # Conflicting CPUs column in vInfo
            "Memory": [1024, 2048],
        }
    )
    df_vcpu = pd.DataFrame(
        {
            "VM": ["vm-1", "vm-2"],
            "CPUs": [2, 4],  # Correct CPU counts from vCPU sheet
        }
    )
    df_vmem = pd.DataFrame(
        {
            "VM": ["vm-1", "vm-2"],
            "Size MiB": [2048, 4096],  # Correct Memory sizes from vMemory sheet
        }
    )
    df_vpart = pd.DataFrame(
        {
            "VM": ["vm-1", "vm-1", "vm-2"],
            "Disk": ["C:\\", "D:\\", "C:\\"],
            "Capacity MiB": [10000, 20000, 30000],
            "Consumed MiB": [2000, 4000, 6000],
        }
    )

    file_dict = {
        "vInfo": df_vinfo,
        "vCPU": df_vcpu,
        "vMemory": df_vmem,
        "vPartition": df_vpart,
    }

    result = process_inventory_upload(file_dict)

    # Check merged and target columns are present
    assert "CPUs" in result.columns
    assert "Size MiB" in result.columns
    assert "Capacity MiB" in result.columns
    assert "Consumed MiB" in result.columns

    # Verify joined/aggregated values
    assert result.loc[result["VM"] == "vm-1", "CPUs"].values[0] == 2
    assert result.loc[result["VM"] == "vm-2", "CPUs"].values[0] == 4

    assert result.loc[result["VM"] == "vm-1", "Size MiB"].values[0] == 2048
    assert result.loc[result["VM"] == "vm-2", "Size MiB"].values[0] == 4096

    # vm-1 capacity: 10000 + 20000 = 30000. vm-1 consumed: 2000 + 4000 = 6000
    assert result.loc[result["VM"] == "vm-1", "Capacity MiB"].values[0] == 30000
    assert result.loc[result["VM"] == "vm-1", "Consumed MiB"].values[0] == 6000

    # vm-2 capacity: 30000. vm-2 consumed: 6000
    assert result.loc[result["VM"] == "vm-2", "Capacity MiB"].values[0] == 30000
    assert result.loc[result["VM"] == "vm-2", "Consumed MiB"].values[0] == 6000


def test_process_inventory_upload_rvtools_fallback_storage() -> None:
    """Tests that if vPartition has no data, Capacity MiB falls back to Total disk capacity MiB and Consumed MiB falls back to In Use MiB."""
    df_vinfo = pd.DataFrame(
        {
            "VM": ["vm-1"],
            "CPUs": [2],
            "Memory": [2048],
            "Total disk capacity MiB": [50000],  # Hardware disk capacity fallback
            "In Use MiB": [15000],  # Hardware used disk fallback
        }
    )
    df_vcpu = pd.DataFrame({"VM": ["vm-1"], "CPUs": [2]})
    df_vmem = pd.DataFrame({"VM": ["vm-1"], "Size MiB": [2048]})
    df_vpart = pd.DataFrame(
        columns=["VM", "Capacity MiB", "Consumed MiB"]
    )  # Empty partition sheet

    file_dict = {
        "vInfo": df_vinfo,
        "vCPU": df_vcpu,
        "vMemory": df_vmem,
        "vPartition": df_vpart,
    }

    result = process_inventory_upload(file_dict)

    # Verify that capacity and consumed fallback worked
    assert "Capacity MiB" in result.columns
    assert "Consumed MiB" in result.columns
    assert result.loc[result["VM"] == "vm-1", "Capacity MiB"].values[0] == 50000
    assert result.loc[result["VM"] == "vm-1", "Consumed MiB"].values[0] == 15000


def test_process_inventory_upload_failsafe_fallbacks() -> None:
    """Tests that if sheets fail to join (e.g. mismatched VM names or empty sheets), CPUs and Size MiB fall back to vInfo values."""
    df_vinfo = pd.DataFrame(
        {
            "VM": ["vm-1"],
            "CPUs": [8],  # Fail-safe CPUs in vInfo
            "Memory": [16384],  # Fail-safe Memory in vInfo
        }
    )
    df_vcpu = pd.DataFrame({"VM": ["vm-mismatched"], "CPUs": [2]})
    df_vmem = pd.DataFrame({"VM": ["vm-mismatched"], "Size MiB": [2048]})
    df_vpart = pd.DataFrame(columns=["VM", "Capacity MiB", "Consumed MiB"])

    file_dict = {
        "vInfo": df_vinfo,
        "vCPU": df_vcpu,
        "vMemory": df_vmem,
        "vPartition": df_vpart,
    }

    result = process_inventory_upload(file_dict)

    # CPUs and Size MiB should safely fall back to the vInfo values since join was empty/mismatched
    assert "CPUs" in result.columns
    assert "Size MiB" in result.columns
    assert result.loc[result["VM"] == "vm-1", "CPUs"].values[0] == 8
    assert result.loc[result["VM"] == "vm-1", "Size MiB"].values[0] == 16384


def test_transform_in_memory_vmware() -> None:
    """Tests that _transform_in_memory outputs exactly the official Google Cloud Migration Center manual CSV import headers and units."""
    df_info = pd.DataFrame(
        {
            "VM": ["vm-1"],
            "VM UUID": ["vm-uuid-1"],
            "Primary IP Address": ["10.0.0.1"],
            "Powerstate": ["poweredOn"],
            "OS according to the VMware Tools": ["Ubuntu Linux (64-bit)"],
            "CPUs": [2.0],
            "Size MiB": [2048.0],
            "Capacity MiB": [30000.0],
            "Consumed MiB": [24000.0],
        }
    )

    transformed = _transform_in_memory(df_info, pd.DataFrame(), "vmware")
    df_vms = transformed["vms"]

    # Verify correct official headers are present
    assert "MachineId" in df_vms.columns
    assert "MachineName" in df_vms.columns
    assert "PrimaryIPAddress(optional)" in df_vms.columns
    assert "TotalDiskAllocatedGiB" in df_vms.columns
    assert "TotalDiskUsedGiB" in df_vms.columns
    assert "AllocatedProcessorCoreCount" in df_vms.columns
    assert "MemoryGiB" in df_vms.columns
    assert "OsName" in df_vms.columns
    assert "OsType(optional)" in df_vms.columns
    assert "MachineStatus(optional)" in df_vms.columns

    # Verify unit conversions (MiB to GiB) and mappings
    assert (
        df_vms.loc[df_vms["MachineName"] == "vm-1", "MachineId"].values[0]
        == "vm-uuid-1"
    )
    assert (
        df_vms.loc[
            df_vms["MachineName"] == "vm-1", "PrimaryIPAddress(optional)"
        ].values[0]
        == "10.0.0.1"
    )
    assert (
        df_vms.loc[
            df_vms["MachineName"] == "vm-1", "AllocatedProcessorCoreCount"
        ].values[0]
        == 2.0
    )
    assert (
        df_vms.loc[df_vms["MachineName"] == "vm-1", "MemoryGiB"].values[0] == 2.0
    )  # 2048 / 1024
    assert (
        df_vms.loc[df_vms["MachineName"] == "vm-1", "TotalDiskAllocatedGiB"].values[0]
        == 30000.0 / 1024.0
    )
    assert (
        df_vms.loc[df_vms["MachineName"] == "vm-1", "TotalDiskUsedGiB"].values[0]
        == 24000.0 / 1024.0
    )
    assert (
        df_vms.loc[df_vms["MachineName"] == "vm-1", "MachineStatus(optional)"].values[0]
        == "running"
    )


def test_process_inventory_upload_fallback() -> None:
    """Tests that process_inventory_upload returns the first sheet as fallback if formats don't match."""
    df_any = pd.DataFrame(
        {
            "VMName": ["vm-1"],
            "Cores": [2],
        }
    )
    file_dict = {"some_other_sheet": df_any}
    result = process_inventory_upload(file_dict)
    pd.testing.assert_frame_equal(result, df_any)
