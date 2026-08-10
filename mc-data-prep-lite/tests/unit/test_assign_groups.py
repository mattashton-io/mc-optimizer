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

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.assign_groups import assign_assets_to_groups


@pytest.mark.asyncio
async def test_assign_assets_to_groups_with_nan_in_csv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Set mock environment variables
    monkeypatch.setenv("GCP_PROJECT_ID", "test-project")
    monkeypatch.setenv("GCP_LOCATION", "us-central1")

    # Mock tool_context to return a CSV with NaN and whitespace in MachineId
    csv_data = "MachineId,OtherCol\nvm-1,foo\n,bar\nvm-2,baz\n  \n"
    mock_part = MagicMock()
    mock_part.text = csv_data
    mock_part.inline_data = None

    mock_tool_context = MagicMock()
    mock_tool_context.load_artifact = AsyncMock(return_value=mock_part)

    # Mock google auth
    mock_credentials = MagicMock()
    mock_credentials.token = "fake-token"
    mock_auth_default = MagicMock(return_value=(mock_credentials, "test-project"))

    # Mock MigrationCenterClient
    mock_client_instance = MagicMock()
    mock_client_instance.get_group.return_value = MagicMock()  # Group already exists

    # Mock requests.post
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "Success"

    with (
        patch("google.auth.default", mock_auth_default),
        patch(
            "app.assign_groups.migrationcenter_v1.MigrationCenterClient",
            return_value=mock_client_instance,
        ),
        patch("requests.post", return_value=mock_response) as mock_post,
    ):
        res = await assign_assets_to_groups(
            group_id="all-servers", asset_ids=None, tool_context=mock_tool_context
        )

        assert "Success: Assigned 2 assets" in res

        # Verify the requested assets in the mock API call
        _called_args, called_kwargs = mock_post.call_args
        called_json = called_kwargs["json"]
        assert called_json["assets"]["assetIds"] == [
            "projects/test-project/locations/us-central1/assets/vm-1",
            "projects/test-project/locations/us-central1/assets/vm-2",
        ]


@pytest.mark.asyncio
async def test_assign_assets_to_groups_with_mixed_types_in_param(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Set mock environment variables
    monkeypatch.setenv("GCP_PROJECT_ID", "test-project")
    monkeypatch.setenv("GCP_LOCATION", "us-central1")

    # Mock google auth
    mock_credentials = MagicMock()
    mock_credentials.token = "fake-token"
    mock_auth_default = MagicMock(return_value=(mock_credentials, "test-project"))

    # Mock MigrationCenterClient
    mock_client_instance = MagicMock()
    mock_client_instance.get_group.return_value = MagicMock()  # Group already exists

    # Mock requests.post
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "Success"

    with (
        patch("google.auth.default", mock_auth_default),
        patch(
            "app.assign_groups.migrationcenter_v1.MigrationCenterClient",
            return_value=mock_client_instance,
        ),
        patch("requests.post", return_value=mock_response) as mock_post,
    ):
        # Passing list containing numbers, None, and strings
        res = await assign_assets_to_groups(
            group_id="all-servers",
            asset_ids=["vm-3", None, 123.0],
            tool_context=MagicMock(),
        )

        assert "Success: Assigned 2 assets" in res

        # Verify correct string conversion and filtering
        _called_args, called_kwargs = mock_post.call_args
        called_json = called_kwargs["json"]
        assert called_json["assets"]["assetIds"] == [
            "projects/test-project/locations/us-central1/assets/vm-3",
            "projects/test-project/locations/us-central1/assets/123.0",
        ]
