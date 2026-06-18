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
# See the License for the specific language governing permissions and
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
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from .data_prep import transform_infrastructure_data, add_labels_to_tag_file, get_parsed_vms, upload_file_to_gcs
from .import_data import import_data_to_migration_center
from .assign_groups import assign_assets_to_groups
from .update_asset_labels import add_labels_post_import

_, project_id = google.auth.default()
os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
os.environ["GOOGLE_CLOUD_LOCATION"] = "global"
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"

class ResilientGemini(Gemini):
    """Subclass of Gemini that filters out unsupported mime types to avoid 400 errors."""
    
    @override
    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        # Filter unsupported mime types
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
                    # Normalize CSV mime type
                    if "csv" in mime_type.lower():
                        if part.inline_data: part.inline_data.mime_type = "text/csv"
                        if part.file_data: part.file_data.mime_type = "text/csv"
                        mime_type = "text/csv"
                    
                    # Gemini 1.5 supported types
                    # https://cloud.google.com/vertex-ai/generative-ai/docs/model-reference/gemini#supported_mime_types
                    supported = (
                        mime_type.startswith("image/") or
                        mime_type.startswith("video/") or
                        mime_type.startswith("audio/") or
                        mime_type.startswith("text/") or
                        mime_type == "application/pdf"
                    )
                    
                    if not supported:
                        # Skip unsupported binary files (like .xlsx) to avoid 400 INVALID_ARGUMENT
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
You have access to tools for:
1. Uploading files to a GCS bucket. Use this whenever a user provides a file in the chat that needs to be processed.
2. Transforming raw infrastructure exports (VMware, Hyper-V) stored in GCS into MC-compliant CSV formats in GCS.
3. Getting a list of all parsed VMs from GCS with their IDs and attributes.
4. Adding/updating labels (tags) for specific VM IDs in the `tagInfo.csv` file in GCS.
5. Importing generated CSV files from GCS into Migration Center. This tool uploads data from GCS to a new import job.
6. Assigning imported Migration Center assets into groups (e.g. VMware vs Hyper-V groups).
7. Syncing/Applying asset labels in Migration Center based on the `tagInfo.csv` in GCS. This should be called AFTER the import is completed to ensure labels appear in the "Labels" column in Migration Center.

When a user uploads a file to the chat, you MUST first upload it to the GCS bucket using `upload_file_to_gcs`. 
Place VMware exports in `exports/vmware-exports/` and Hyper-V exports in `exports/hyperv-exports/`.

When asked to label servers, you should:
a) Use `add_labels_to_tag_file` to update the CSV in GCS.
b) Run the import using `import_data_to_migration_center`.
c) Use `add_labels_post_import` AFTER the import succeeds to apply those labels to the live assets in Migration Center.

Use the upload_file_to_gcs tool to move local files or chat-provided files to the project GCS bucket.
Use the transform_infrastructure_data tool when asked to process or ingest CSV files from RVTools or Hyper-V. It will look for files in GCS.
Use the get_parsed_vms tool when asked to show, list, or query the parsed VMs and find their MachineIds.
Use the add_labels_to_tag_file tool to add labels to the tagInfo.csv in GCS.
Use the import_data_to_migration_center tool to upload or import the generated data from GCS.
Use the assign_assets_to_groups tool to group assets inside Migration Center.
Use the add_labels_post_import tool to sync labels from tagInfo.csv to the live assets in Migration Center AFTER import.""",
    tools=[
        upload_file_to_gcs,
        transform_infrastructure_data, 
        get_parsed_vms,
        add_labels_to_tag_file,
        import_data_to_migration_center, 
        assign_assets_to_groups,
        add_labels_post_import
    ],
)

app = App(
    root_agent=root_agent,
    name="app",
)
