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

from app.data_prep import process_inventory_upload


def test_process_inventory_upload_standard_mc_csv() -> None:
    """Tests that a standard Migration Center CSV is returned unmodified."""
    df_single = pd.DataFrame(
        {
            "VM": ["vm-1", "vm-2"],
            "vCPU": [2, 4],
            "Memory (MiB)": [2048, 4096],
        }
    )
    file_dict = {"default": df_single}
    result = process_inventory_upload(file_dict)
    pd.testing.assert_frame_equal(result, df_single)


def test_process_inventory_upload_rvtools_format() -> None:
    """Tests that RVTools format sheets are correctly aggregated, joined, and renamed."""
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
            "CPUs": [2, 4],  # Correct vCPU counts from vCPU sheet
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
            "Free MiB": [2000, 4000, 6000],
        }
    )

    file_dict = {
        "vInfo": df_vinfo,
        "vCPU": df_vcpu,
        "vMemory": df_vmem,
        "vPartition": df_vpart,
    }

    result = process_inventory_upload(file_dict)

    # Check merged and renamed columns are present
    assert "vCPU" in result.columns
    assert "Memory (MiB)" in result.columns
    assert "Total storage capacity (MiB)" in result.columns
    assert "Total free storage (MiB)" in result.columns

    # Verify joined/aggregated values
    assert result.loc[result["VM"] == "vm-1", "vCPU"].values[0] == 2
    assert result.loc[result["VM"] == "vm-2", "vCPU"].values[0] == 4

    assert result.loc[result["VM"] == "vm-1", "Memory (MiB)"].values[0] == 2048
    assert result.loc[result["VM"] == "vm-2", "Memory (MiB)"].values[0] == 4096

    # vm-1 capacity: 10000 + 20000 = 30000. vm-1 free: 2000 + 4000 = 6000
    assert (
        result.loc[result["VM"] == "vm-1", "Total storage capacity (MiB)"].values[0]
        == 30000
    )
    assert (
        result.loc[result["VM"] == "vm-1", "Total free storage (MiB)"].values[0] == 6000
    )

    # vm-2 capacity: 30000. vm-2 free: 6000
    assert (
        result.loc[result["VM"] == "vm-2", "Total storage capacity (MiB)"].values[0]
        == 30000
    )
    assert (
        result.loc[result["VM"] == "vm-2", "Total free storage (MiB)"].values[0] == 6000
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
