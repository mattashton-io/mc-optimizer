import os
import subprocess

import google.auth


def get_project_id():
    """
    Returns the project ID, prioritizing environment variables, then gcloud config,
    and finally Application Default Credentials.
    """
    # 1. Check environment variables
    project_id = os.environ.get("GCP_PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT")
    if project_id:
        return project_id

    # 2. Check gcloud config
    try:
        # We use check=False to avoid raising an exception if gcloud is not installed
        result = subprocess.run(
            ["gcloud", "config", "get-value", "project"],
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode == 0:
            project_id = result.stdout.strip()
            if project_id and project_id != "(unset)":
                # Cache it in environment to avoid repeated subprocess calls
                os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
                return project_id
    except FileNotFoundError:
        # gcloud is not installed
        pass
    except Exception:
        pass

    # 3. Check Application Default Credentials
    try:
        _, project_id = google.auth.default()
        if project_id:
            os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
            return project_id
    except Exception:
        pass

    return None
