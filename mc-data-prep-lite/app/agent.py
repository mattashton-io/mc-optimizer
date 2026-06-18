# ruff: noqa
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
# limitations under the License.

import datetime
from zoneinfo import ZoneInfo
import os
import google.auth

from typing import AsyncGenerator
from typing_extensions import override
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.plugins.save_files_as_artifacts_plugin import SaveFilesAsArtifactsPlugin
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from .data_prep import (
    process_uploaded_infrastructure_file, 
    get_parsed_vms, 
    add_labels_to_staged_artifact,
    upload_file_to_gcs
)
from .import_data import import_data_to_migration_center
from .assign_groups import assign_assets_to_groups, list_migration_center_groups
from .update_asset_labels import add_labels_post_import

try:
    _, project_id = google.auth.default()
    os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
except Exception:
    pass

os.environ["GOOGLE_CLOUD_LOCATION"] = "global"
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"

class ResilientGemini(Gemini):
    """Subclass of Gemini that filters out unsupported mime types to avoid 400 errors."""
    
    @override
    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        llm_request = llm_request.model_copy(deep=True)
        
        for content in llm_request.contents:
            if not content.parts:
                continue
            
            filtered_parts = []
            for part in content.parts:
                mime_type = None
                if part.inline_data:
                    mime_type = part.inline_data.mime_type
                elif part.file_data:
                    mime_type = part.file_data.mime_type
                
                if mime_type:
                    if "csv" in mime_type.lower():
                        if part.inline_data: part.inline_data.mime_type = "text/csv"
                        if part.file_data: part.file_data.mime_type = "text/csv"
                        mime_type = "text/csv"
                    
                    supported = (
                        mime_type.startswith("image/") or
                        mime_type.startswith("video/") or
                        mime_type.startswith("audio/") or
                        mime_type.startswith("text/") or
                        mime_type == "application/pdf"
                    )
                    
                    if not supported:
                        filename = "uploaded_file"
                        if part.file_data:
                            filename = part.file_data.file_uri.split("/")[-1]
                        elif part.inline_data:
                            filename = "binary_artifact"
                        
                        filtered_parts.append(types.Part(text=f"[Artifact Uploaded: {filename}]"))
                        continue
                
                filtered_parts.append(part)
            content.parts = filtered_parts
            
        async for response in super().generate_content_async(llm_request, stream):
            yield response

root_agent = Agent(
    name="root_agent",
    model=ResilientGemini(
        model="gemini-flash-latest",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction="""You are a GCP Migration Data Prep Agent. 
Your goal is to help users prepare, tag, import, and group their on-premises workload data for Migration Center.

### Important: Handling Uploads
When a user uploads a file, you might see a placeholder like `[Artifact Uploaded: filename.xlsx]`. 
This indicates that the file was successfully uploaded to the chat session as an ADK Artifact.

### Generic Template Detection
If a user uploads a .csv file that matches Migration Center manual upload templates (contains 'MachineId', 'MachineName'):
1. **Ask the user** if the source Platform is: 1. Hyper-V 2. Nutanix 3. Proxmox 4. Other.
2. Once identified, use `process_uploaded_infrastructure_file` with the appropriate `format_type`.

### Grouping and Labeling Guidelines
- **Group Assignment**: 
    1. Use `list_migration_center_groups` to show existing groups.
    2. Review imported servers using `get_parsed_vms`.
    3. **Offer 2-3 logical grouping suggestions** (e.g., by OS Type, by Source Platform, by Memory size).
    4. Allow the user to pick a suggestion, an existing group, or provide a new group name.
    5. Use `assign_assets_to_groups` with the chosen `group_id` and list of `asset_ids`.
- **Labeling (Native API)**: 
    - Use `add_labels_post_import` to apply labels via the Migration Center API. 
    - **Performance Note**: If there are many labels, prefer calling `add_labels_post_import` WITHOUT the `labels_dict` argument; it will automatically read from the `staged_labels.csv` session artifact created during data prep.
    - If you need to add custom labels, use `add_labels_to_staged_artifact` first, then call `add_labels_post_import`.
    - Do NOT use `tagInfo.csv` for post-import labeling.
- **tagInfo.csv**: Only use this if provided in the initial set of uploaded files by the user. If provided, `process_uploaded_infrastructure_file` will validate it automatically.

### Workflow:
1. **Request Upload**: Ask the user to upload their export files.
2. **Process**: Call `process_uploaded_infrastructure_file`. 
   - `vmInfo.csv` is REQUIRED. `diskInfo.csv`, `perfInfo.csv`, and `tagInfo.csv` are OPTIONAL.
3. **Review**: Use `get_parsed_vms` to list VMs and attributes.
4. **Import**: Use `import_data_to_migration_center`.
5. **Group/Label**: Follow the guidelines above to suggest groups and apply labels AFTER import.

### Guidelines:
- Do NOT save uploaded files to local disk.
- If you encounter a mime type error, you can still process the file as an artifact.""",
    tools=[
        process_uploaded_infrastructure_file,
        get_parsed_vms,
        import_data_to_migration_center, 
        list_migration_center_groups,
        assign_assets_to_groups,
        add_labels_post_import,
        add_labels_to_staged_artifact,
        upload_file_to_gcs
    ],
)

app = App(
    root_agent=root_agent,
    name="app",
    plugins=[SaveFilesAsArtifactsPlugin()],
)
