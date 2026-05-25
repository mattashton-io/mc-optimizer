from unittest.mock import MagicMock, patch
import pytest
from app.reporting import setup_migration_preferences, create_tco_report

@patch("app.reporting.get_gcp_context")
@patch("app.reporting.migrationcenter_v1.MigrationCenterClient")
def test_setup_migration_preferences(mock_client_class, mock_ctx):
    # Mock GCP context to return test-project and us-central1
    mock_ctx.return_value = ("test-project", "us-central1")
    
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    
    # Mock get_preference_set to raise Exception so it attempts creation
    mock_client.get_preference_set.side_effect = Exception("Not found")
    
    # Run the setup
    res = setup_migration_preferences()
    
    assert "test-project" in res
    assert mock_client.create_preference_set.call_count == 4

@patch("app.reporting.get_gcp_context")
@patch("app.reporting.migrationcenter_v1.MigrationCenterClient")
def test_create_tco_report(mock_client_class, mock_ctx):
    # Mock GCP context
    mock_ctx.return_value = ("test-project", "us-central1")
    
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    
    # Mock asset listing and group checking
    mock_client.list_assets.return_value = []
    mock_client.get_group.side_effect = Exception("Not found")
    
    # Run creation
    res = create_tco_report()
    
    assert "test-project" in res
    assert mock_client.create_group.call_count == 3
    assert mock_client.create_report_config.call_count == 1
    assert mock_client.create_report.call_count == 1
