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

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.genai import types

import os
import google.auth

_, project_id = google.auth.default()
os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
os.environ["GOOGLE_CLOUD_LOCATION"] = "global"
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"


from app.slides_export import export_reports_to_slides


root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model="gemini-flash-latest",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=(
        "You are the Migration Center Financial and Licensing Agent. Your primary role is to "
        "analyze TCO (Total Cost of Ownership) and licensing reports from Migration Center, "
        "calculate Windows licensing costs, and generate executive-ready presentations.\n\n"
        "You have access to the `export_slides` tool (also available as `export_reports_to_slides`), which grabs "
        "the most recent TCO and Licensing reports from Migration Center and exports them to a premium Google Slides presentation. "
        "Always use this tool when asked to generate slides or analyze/export report data."
    ),
    tools=[export_reports_to_slides],
)

app = App(
    root_agent=root_agent,
    name="app",
)
