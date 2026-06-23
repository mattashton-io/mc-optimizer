import os
import tempfile
import time

import requests
from google.adk.tools import ToolContext
from google.cloud import migrationcenter_v1

from .app_utils.project_utils import get_project_id


async def import_data_to_migration_center(tool_context: ToolContext) -> str:
    """Imports generated CSV files (vmInfo.csv, diskInfo.csv, tagInfo.csv) from session artifacts into Migration Center.
    
    Returns:
        A string indicating success or failure.
    """
    project_id = get_project_id()
    location = os.environ.get("GCP_LOCATION") or os.environ.get("GOOGLE_CLOUD_LOCATION") or "us-central1"

    if location == "global":
        location = "us-central1"

    if not project_id:
        return "Error: GCP Project ID could not be determined."

    print(f"Using project: {project_id}, location: {location}")

    # Initialize Migration Center client
    try:
        client = migrationcenter_v1.MigrationCenterClient()
    except Exception as e:
        return f"Error initializing Migration Center client: {e}"

    job_id = f"manual-import-{int(time.time())}"
    parent = f"projects/{project_id}/locations/{location}"

    print(f"Creating asset source in {parent}...")
    try:
        source_id = f"source-{int(time.time())}"
        source_op = client.create_source(
            parent=parent,
            source_id=source_id,
            source={"display_name": f"Source {time.strftime('%Y%m%d-%H%M%S')}"}
        )
        source = source_op.result()
        print(f"Asset source created: {source.name}")
    except Exception as e:
        return f"Error: Failed to create asset source in project '{project_id}' at '{location}': {e}."

    import_job = {
        "display_name": f"Manual Import {time.strftime('%Y%m%d-%H%M%S')}",
        "asset_source": source.name
    }
    request = migrationcenter_v1.CreateImportJobRequest(
        parent=parent,
        import_job_id=job_id,
        import_job=import_job,
    )

    print(f"Creating import job {job_id}...")
    try:
        operation = client.create_import_job(request=request)
        response = operation.result()
        job_name = response.name
        print(f"Import job created: {job_name}")
    except Exception as e:
        return f"Error: Failed to create import job: {e}"

    files = ["vmInfo.csv", "diskInfo.csv", "tagInfo.csv"]
    uploaded_files = []
    failed_files = []

    with tempfile.TemporaryDirectory() as tmp_dir:
        for file_name in files:
            local_path = os.path.join(tmp_dir, file_name)

            print(f"Loading {file_name} from session artifacts...")
            try:
                part = await tool_context.load_artifact(file_name)
                if not part:
                    raise ValueError("Artifact not found in session.")

                content_bytes = None
                if part.inline_data:
                    content_bytes = part.inline_data.data
                elif part.text:
                    content_bytes = part.text.encode("utf-8")

                if not content_bytes:
                    raise ValueError("Artifact is empty.")

                with open(local_path, "wb") as f:
                    f.write(content_bytes)
            except Exception as e:
                print(f"File {file_name} not found or error loading from artifacts: {e}")
                if file_name == "vmInfo.csv":
                     failed_files.append(file_name)
                continue

            import_data_file = {"format": "IMPORT_JOB_FORMAT_STRATOZONE_CSV"}

            req = migrationcenter_v1.CreateImportDataFileRequest(
                parent=job_name,
                import_data_file_id=file_name.split(".")[0].lower(),
                import_data_file=import_data_file,
            )

            print(f"Creating import data file resource for {file_name}...")
            try:
                op = client.create_import_data_file(request=req)
                resp = op.result()
                upload_uri = resp.upload_file_info.signed_uri

                headers = dict(resp.upload_file_info.headers)
                if not headers:
                    headers = {"Content-Type": "application/octet-stream"}

                print(f"Uploading file {file_name} to signed URL...")
                with open(local_path, "rb") as f:
                    put_resp = requests.put(
                        upload_uri,
                        data=f,
                        headers=headers,
                    )
                    if put_resp.status_code == 200:
                        print(f"Successfully uploaded {file_name}")
                        uploaded_files.append(file_name)
                    else:
                        print(f"Failed to upload {file_name}: {put_resp.status_code}")
                        failed_files.append(file_name)
            except Exception as e:
                print(f"Failed to process {file_name}: {e}")
                failed_files.append(file_name)

    if failed_files:
        return f"Error: Import aborted due to missing or failed file uploads: {failed_files}. Uploaded: {uploaded_files}. Ensure you have run data transformation first."

    def wait_for_job_state(job_name, target_states, transitioning_states, timeout_sec=600):
        start_time = time.time()
        while True:
            if time.time() - start_time > timeout_sec:
                return None, f"Timeout: Job {job_name} timed out after {timeout_sec}s while waiting for states {target_states}."

            try:
                job = client.get_import_job(name=job_name)
                state = int(job.state)
                if state in target_states:
                    return job, None
                if state not in transitioning_states:
                    return job, None

                print(f"Job state is {job.state} ({state}). Waiting...")
                time.sleep(10)
            except Exception as e:
                return None, f"Error polling job state: {e}"

    print(f"Validating import job {job_name}...")
    try:
        client.validate_import_job(name=job_name)
        print("Waiting for validation to complete...")
        job, error = wait_for_job_state(job_name, [7, 6, 3, 4], [5, 1, 2])
        if error:
            return error

        print(f"Job state after validation: {job.state}")

        if int(job.state) in [4, 6]:
             report = job.validation_report
             error_msgs = []
             if report:
                 if report.file_validations:
                     for fv in report.file_validations:
                         for err in fv.file_errors:
                             error_msgs.append(f"File {fv.file_name}: {err.error_details}")
                         for row_err in fv.row_errors:
                             for err in row_err.errors:
                                 error_msgs.append(f"File {fv.file_name} Row {row_err.row_number}: {err.error_details}")
                 if hasattr(report, 'job_errors') and report.job_errors:
                     for err in report.job_errors:
                         error_msgs.append(f"Job: {err.error_details}")
             return f"Error: Validation failed with state {job.state}. Errors: {'; '.join(error_msgs[:10])}{'...' if len(error_msgs) > 10 else ''}"

        if int(job.state) not in [7, 3]:
             return f"Error: Validation failed or job stuck. State: {job.state}. Please ensure the generated CSV files are valid Migration Center exports."
    except Exception as e:
        return f"Error: Validation failed: {e}"

    print(f"Running import job {job_name}...")
    try:
        client.run_import_job(name=job_name)
        print("Waiting for import job to complete...")
        job, error = wait_for_job_state(job_name, [3, 4], [1, 2, 5, 7])
        if error:
            return error

        print(f"Job state after run: {job.state}")
        if int(job.state) != 3:
            report = job.execution_report
            error_msgs = []
            if report and report.execution_errors:
                for err in report.execution_errors:
                    error_msgs.append(f"{err.error_details}")
            return f"Error: Run failed. State: {job.state}. Errors: {'; '.join(error_msgs[:10])}"
    except Exception as e:
        return f"Error: Run failed: {e}"

    return f"Success: Data imported and processed in job {job_name}. Uploaded files: {uploaded_files}. Assets are now available in Migration Center."
