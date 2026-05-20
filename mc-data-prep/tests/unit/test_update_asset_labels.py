import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
from app.update_asset_labels import add_labels_post_import

class TestUpdateAssetLabels(unittest.TestCase):
    
    @patch('app.update_asset_labels.os.path.exists')
    @patch('app.update_asset_labels.pd.read_csv')
    @patch('app.update_asset_labels.google.auth.default')
    @patch('app.update_asset_labels.migrationcenter_v1.MigrationCenterClient')
    def test_add_labels_post_import_success(self, mock_client_class, mock_auth, mock_read_csv, mock_exists):
        # 1. Setup mock csv exists and contents
        mock_exists.return_value = True
        
        # tagInfo.csv with custom/alternative headers to test robustness!
        mock_df = pd.DataFrame({
            "MachineId": ["vm-1", "vm-2"],
            "Key": ["env", "owner"],
            "Value": ["prod", "team-a"]
        })
        mock_read_csv.return_value = mock_df
        
        # 2. Setup mock google auth
        mock_auth.return_value = (None, "test-project-123")
        
        # 3. Setup mock client and returned assets
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        mock_asset_1 = MagicMock()
        mock_asset_1.name = "projects/test-project-123/locations/us-central1/assets/vm-1"
        mock_asset_1.labels = {"original": "label"}
        
        mock_asset_2 = MagicMock()
        mock_asset_2.name = "projects/test-project-123/locations/us-central1/assets/vm-2"
        mock_asset_2.labels = {}
        
        mock_client.list_assets.return_value = [mock_asset_1, mock_asset_2]
        
        # 4. Mock the LRO return value for update_asset
        mock_op = MagicMock()
        mock_client.update_asset.return_value = mock_op
        
        # 5. Call the function
        result = add_labels_post_import()
        
        # 6. Assert results and calls
        self.assertIn("Successfully updated: 2 assets", result)
        self.assertIn("vm-1 updated successfully", result)
        self.assertIn("vm-2 updated successfully", result)
        
        # Verify update_asset was called twice
        self.assertEqual(mock_client.update_asset.call_count, 2)
        
        # Verify first call merged original labels with the new one
        first_call_args = mock_client.update_asset.call_args_list[0][1]['request']
        self.assertEqual(first_call_args.asset.labels, {"original": "label", "env": "prod"})
        
        # Verify second call set the new label
        second_call_args = mock_client.update_asset.call_args_list[1][1]['request']
        self.assertEqual(second_call_args.asset.labels, {"owner": "team-a"})

    @patch('app.update_asset_labels.os.path.exists')
    @patch('app.update_asset_labels.pd.read_csv')
    @patch('app.update_asset_labels.google.auth.default')
    @patch('app.update_asset_labels.migrationcenter_v1.MigrationCenterClient')
    def test_add_labels_post_import_no_update_needed(self, mock_client_class, mock_auth, mock_read_csv, mock_exists):
        # 1. Setup mock csv exists and contents
        mock_exists.return_value = True
        
        mock_df = pd.DataFrame({
            "Machine Id": ["vm-1"],
            "Tag Category": ["env"],
            "Tag Value": ["prod"]
        })
        mock_read_csv.return_value = mock_df
        
        # 2. Setup mock google auth
        mock_auth.return_value = (None, "test-project-123")
        
        # 3. Setup mock client and returned assets (asset already has the label!)
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        mock_asset_1 = MagicMock()
        mock_asset_1.name = "projects/test-project-123/locations/us-central1/assets/vm-1"
        mock_asset_1.labels = {"env": "prod", "original": "label"}
        
        mock_client.list_assets.return_value = [mock_asset_1]
        
        # 5. Call the function
        result = add_labels_post_import()
        
        # 6. Assert results
        self.assertIn("Successfully updated: 0 assets", result)
        self.assertIn("Skipped (already matching): 1 assets", result)
        self.assertEqual(mock_client.update_asset.call_count, 0)

if __name__ == "__main__":
    unittest.main()
