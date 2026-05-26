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
    
    # Verify sizing strategies
    # Calls 2 and 3 should be rightsized (index 2 and 3 in preferences list)
    # The actual order might depend on the implementation, but let's check what was sent in create_preference_set
    created_prefs = []
    for call in mock_client.create_preference_set.call_args_list:
        if "request" in call.kwargs:
            created_prefs.append(call.kwargs["request"].preference_set)
        elif len(call.args) > 0:
            # Depending on how the SDK handles positional args for request
            # Usually it might be the first arg if not keyworded
            req = call.args[0]
            if hasattr(req, "preference_set"):
                created_prefs.append(req.preference_set)
            else:
                created_prefs.append(req)

    rightsized_prefs = [p for p in created_prefs if "rightsized" in p.display_name.lower()]
    assert len(rightsized_prefs) == 2
    for p in rightsized_prefs:
        assert p.virtual_machine_preferences.sizing_optimization_strategy == 4 # CUSTOM
        c_opt = p.virtual_machine_preferences.custom_sizing_optimization_customization
        assert c_opt.cpu_usage_percentage == 95
        assert c_opt.cpu_safety_buffer_percentage == 20
        assert c_opt.memory_usage_percentage == 90
        assert c_opt.memory_safety_buffer_percentage == 15
        assert c_opt.storage_usage_percentage == 80
        assert c_opt.storage_safety_buffer_percentage == 10


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
