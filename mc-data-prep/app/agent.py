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
from .data_prep import transform_infrastructure_data, add_labels_to_tag_file, get_parsed_vms
from .import_data import import_data_to_migration_center
from .assign_groups import assign_assets_to_groups

_, project_id = google.auth.default()
os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
os.environ["GOOGLE_CLOUD_LOCATION"] = "global"
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"


def get_weather(query: str) -> str:
    """Simulates a web search. Use it get information on weather.

    Args:
        query: A string containing the location to get weather information for.

    Returns:
        A string with the simulated weather information for the queried location.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        return "It's 60 degrees and foggy."
    return "It's 90 degrees and sunny."


def get_current_time(query: str) -> str:
    """Simulates getting the current time for a city.

    Args:
        city: The name of the city to get the current time for.

    Returns:
        A string with the current time information.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        tz_identifier = "America/Los_Angeles"
    else:
        return f"Sorry, I don't have timezone information for query: {query}."

    tz = ZoneInfo(tz_identifier)
    now = datetime.datetime.now(tz)
    return f"The current time for query {query} is {now.strftime('%Y-%m-%d %H:%M:%S %Z%z')}"


root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model="gemini-flash-latest",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction="""You are a GCP Migration Data Prep Agent. 
Your goal is to help users prepare, tag, import, and group their on-premises workload data for Migration Center.
You have access to tools for:
1. Transforming raw infrastructure exports (VMware, Hyper-V) into MC-compliant CSV formats.
2. Getting a list of all parsed VMs with their IDs and attributes.
3. Adding/updating labels (tags) for specific VM IDs, conforming strictly to template headers.
4. Importing generated CSV files into Migration Center.
5. Assigning imported Migration Center assets into groups (e.g. VMware vs Hyper-V groups).

Use the transform_infrastructure_data tool when asked to process or ingest CSV files from RVTools or Hyper-V.
Use the get_parsed_vms tool when asked to show, list, or query the parsed VMs and find their MachineIds.
Use the add_labels_to_tag_file tool when asked to add labels or tags to servers. Ensure you match the exact template structure of (MachineId,Key,Value) by calling this tool.
Use the import_data_to_migration_center tool when asked to upload or import the generated data to Migration Center.
Use the assign_assets_to_groups tool when asked to assign or group assets inside Migration Center.""",
    tools=[
        get_weather, 
        get_current_time, 
        transform_infrastructure_data, 
        get_parsed_vms,
        add_labels_to_tag_file,
        import_data_to_migration_center, 
        assign_assets_to_groups
    ],
)

app = App(
    root_agent=root_agent,
    name="app",
)
