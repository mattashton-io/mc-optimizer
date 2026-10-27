from unittest.mock import MagicMock, patch

import pytest

from app.scan_environment import scan_migration_center_environment


@pytest.mark.asyncio
async def test_scan_migration_center_environment_with_assets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GCP_PROJECT_ID", "test-project")
    monkeypatch.setenv("GCP_LOCATION", "us-central1")

    asset1 = MagicMock()
    asset1.name = "projects/test-project/locations/us-central1/assets/vm-1"
    asset1.machine_details.machine_name = "server-1"
    asset1.machine_details.core_count = 4
    asset1.machine_details.memory_mb = 8192
    asset1.machine_details.disks.total_capacity_bytes = 100 * (1024**3)
    asset1.machine_details.disks.total_free_bytes = 20 * (1024**3)
    asset1.machine_details.guest_os.family.name = "OS_FAMILY_WINDOWS"
    asset1.machine_details.guest_os.os_name = "Windows Server 2022"
    asset1.machine_details.power_state.name = "ACTIVE"
    asset1.machine_details.platform._pb.WhichOneof.return_value = "generic_details"
    asset1.labels = {"env": "prod"}

    asset2 = MagicMock()
    asset2.name = "projects/test-project/locations/us-central1/assets/vm-2"
    asset2.machine_details.machine_name = "server-2"
    asset2.machine_details.core_count = 8
    asset2.machine_details.memory_mb = 16384
    asset2.machine_details.disks.total_capacity_bytes = 200 * (1024**3)
    asset2.machine_details.disks.total_free_bytes = 50 * (1024**3)
    asset2.machine_details.guest_os.family.name = "OS_FAMILY_LINUX"
    asset2.machine_details.guest_os.os_name = "Ubuntu 22.04"
    asset2.machine_details.power_state.name = "SUSPENDED"
    asset2.machine_details.platform._pb.WhichOneof.return_value = "vmware_details"
    asset2.labels = {"env": "dev"}

    group1 = MagicMock()
    group1.name = "projects/test-project/locations/us-central1/groups/all-servers"
    group1.display_name = "All Servers"
    group1.size = 2

    source1 = MagicMock()
    source1.name = "projects/test-project/locations/us-central1/sources/src-1"
    source1.display_name = "RVTools Upload"
    source1.state.name = "ACTIVE"

    mock_client = MagicMock()
    mock_client.list_assets.return_value = [asset1, asset2]
    mock_client.list_groups.return_value = [group1]
    mock_client.list_sources.return_value = [source1]

    with patch(
        "app.scan_environment.migrationcenter_v1.MigrationCenterClient",
        return_value=mock_client,
    ):
        result = await scan_migration_center_environment()

    assert "Total Imported VMs / Servers**: **2**" in result
    assert "Total vCPUs / Cores**: 12" in result
    assert "24.0 GiB" in result
    assert "Windows Server 2022" in result
    assert "Ubuntu 22.04" in result
    assert "All Servers" in result
    assert "`env=prod`" in result
