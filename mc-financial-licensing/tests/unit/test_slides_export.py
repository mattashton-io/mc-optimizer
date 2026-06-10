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

from unittest.mock import MagicMock, patch
import pytest

from google.cloud import migrationcenter_v1
from app.slides_export import export_reports_to_slides


def test_export_reports_to_slides_mocked():
    """Test that export_reports_to_slides successfully runs with mocked Google API clients."""
    
    # Mock google auth
    mock_creds = MagicMock()
    with patch("google.auth.default", return_value=(mock_creds, "mock-project")):
        
        # Mock migration center client
        mock_mc_client_inst = MagicMock()
        mock_config = MagicMock()
        mock_config.name = "projects/mock-project/locations/us-east4/reportConfigs/cfg1"
        mock_mc_client_inst.list_report_configs.return_value = [mock_config]
        
        # Report mocks
        mock_report_tco = MagicMock()
        mock_report_tco.state = migrationcenter_v1.Report.State.SUCCEEDED
        mock_report_tco.type_ = migrationcenter_v1.Report.Type.TOTAL_COST_OF_OWNERSHIP
        mock_report_tco.create_time = 100
        mock_report_tco.display_name = "mock-tco-report"
        
        # Mock group findings in summary
        gf_tco = MagicMock()
        gf_tco.display_name = "all-assets"
        gf_tco.group = "all-assets"
        
        # Mock preferences findings
        pf_tco_1yr = MagicMock()
        pf_tco_1yr.display_name = "1-year CUD like-for-like"
        pf_tco_1yr.monthly_cost_compute.units = 10000
        pf_tco_1yr.monthly_cost_compute.nanos = 0
        pf_tco_1yr.monthly_cost_storage.units = 2000
        pf_tco_1yr.monthly_cost_storage.nanos = 0
        pf_tco_1yr.monthly_cost_os_license.units = 5000
        pf_tco_1yr.monthly_cost_os_license.nanos = 0
        pf_tco_1yr.monthly_cost_total.units = 17000
        pf_tco_1yr.monthly_cost_total.nanos = 0
        
        pf_tco_3yr = MagicMock()
        pf_tco_3yr.display_name = "3-year CUD like-for-like"
        pf_tco_3yr.monthly_cost_compute.units = 8000
        pf_tco_3yr.monthly_cost_compute.nanos = 0
        pf_tco_3yr.monthly_cost_storage.units = 2000
        pf_tco_3yr.monthly_cost_storage.nanos = 0
        pf_tco_3yr.monthly_cost_os_license.units = 4500
        pf_tco_3yr.monthly_cost_os_license.nanos = 0
        pf_tco_3yr.monthly_cost_total.units = 14500
        pf_tco_3yr.monthly_cost_total.nanos = 0
        
        gf_tco.preference_set_findings = [pf_tco_1yr, pf_tco_3yr]
        mock_report_tco.summary.group_findings = [gf_tco]
        
        mock_report_lic = MagicMock()
        mock_report_lic.state = migrationcenter_v1.Report.State.SUCCEEDED
        mock_report_lic.type_ = migrationcenter_v1.Report.Type.TYPE_UNSPECIFIED
        mock_report_lic.create_time = 100
        mock_report_lic.display_name = "mock-license-report"
        
        gf_lic = MagicMock()
        gf_lic.display_name = "all-assets"
        gf_lic.group = "all-assets"
        
        pf_lic = MagicMock()
        pf_lic.display_name = "Compute Engine"
        pf_lic.monthly_cost_compute.units = 2000
        pf_lic.monthly_cost_compute.nanos = 0
        pf_lic.monthly_cost_os_license.units = 2200
        pf_lic.monthly_cost_os_license.nanos = 0
        
        gf_lic.preference_set_findings = [pf_lic]
        mock_report_lic.summary.group_findings = [gf_lic]
        
        mock_mc_client_inst.list_reports.return_value = [mock_report_tco, mock_report_lic]
        
        # Mock slides service
        mock_slides_service = MagicMock()
        mock_pres_create = MagicMock()
        mock_pres_create.execute.return_value = {
            "presentationId": "mock-presentation-id",
            "slides": [{"objectId": "mock-slide-1"}]
        }
        mock_slides_service.presentations().create.return_value = mock_pres_create
        
        mock_batch = MagicMock()
        mock_batch.execute.return_value = {}
        mock_slides_service.presentations().batchUpdate.return_value = mock_batch
        
        # Patch clients
        with patch("google.cloud.migrationcenter_v1.MigrationCenterClient", return_value=mock_mc_client_inst):
            with patch("app.slides_export.build", return_value=mock_slides_service):
                result = export_reports_to_slides()
                
                # Check that result contains the mocked presentation ID and markdown formatting
                assert "mock-presentation-id" in result
                assert "mock-tco-report" in result
                assert "mock-license-report" in result
                assert "$10,000.00" in result
                assert "$5,000.00" in result  # OS Pricing for 1-year
                assert "$5,000.00" in result  # OS Credit for 1-year (100% of 5000)
                # For 3-year, OS Pricing is 4500. Credit is 4500 * 5/6 = 3750.
                assert "$3,750.00" in result
