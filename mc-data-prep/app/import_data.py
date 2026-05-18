import os
import time
import google.auth
import requests
from google.cloud import migrationcenter_v1

def import_data_to_migration_center() -> str:
    """Imports generated CSV files (vmInfo.csv, diskInfo.csv) into Migration Center.
    
    It reads project and location from environment variables GCP_PROJECT_ID and GCP_LOCATION.
    It reads files from 'data/output' and uploads them to a new import job.
    
    Returns:
        A string indicating success or failure.
    """
    OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "data", "output")
    
    project_id = os.environ.get("GCP_PROJECT_ID")
    location = os.environ.get("GCP_LOCATION", "us-central1")
    
    if not project_id:
        # Fallback to google.auth.default()
        try:
            _, project_id = google.auth.default()
        except Exception as e:
            return f"Failed to get project ID: {e}"
            
    if not project_id:
        return "GCP_PROJECT_ID environment variable not set and could not be determined."

    print(f"Using project: {project_id}, location: {location}")

    client = migrationcenter_v1.MigrationCenterClient()

    job_id = f"manual-import-{int(time.time())}"
    
    parent = f"projects/{project_id}/locations/{location}"
    print("Creating asset source...")
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
        return f"Failed to create asset source: {e}"

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
        return f"Failed to create import job: {e}"

    files = ["vmInfo.csv", "diskInfo.csv", "tagInfo.csv"]
    uploaded_files = []
    failed_files = []

    for file_name in files:
        file_path = os.path.join(OUTPUT_DIR, file_name)
        if not os.path.exists(file_path):
            print(f"File not found: {file_path}")
            failed_files.append(file_name)
            continue

        import_data_file = {"format": "IMPORT_JOB_FORMAT_STRATOZONE_CSV"}

        req = migrationcenter_v1.CreateImportDataFileRequest(
            parent=job_name,
            import_data_file_id=file_name.replace(".", "-").lower(),
            import_data_file=import_data_file,
        )

        print(f"Creating import data file resource for {file_name}...")
        try:
            op = client.create_import_data_file(request=req)
            resp = op.result()
            upload_uri = resp.upload_file_info.signed_uri
            
            print(f"Uploading file {file_name} to {upload_uri}...")
            with open(file_path, "rb") as f:
                put_resp = requests.put(
                    upload_uri,
                    data=f,
                    headers={
                        "Content-Type": "application/octet-stream",
                        "x-goog-content-length-range": "0,104857600",
                    },
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
        return f"Import completed with failures. Uploaded: {uploaded_files}. Failed: {failed_files}"
    
    def wait_for_job_state(job_name, target_states, transitioning_states):
        while True:
            job = client.get_import_job(name=job_name)
            state = int(job.state)
            if state in target_states:
                return job
            if state not in transitioning_states:
                return job
            print(f"Job state is {state}. Waiting...")
            time.sleep(10)

    print(f"Validating import job {job_name}...")
    try:
        client.validate_import_job(name=job_name)
        print("Waiting for validation to complete (polling state)...")
        # 5: VALIDATING, 7: READY, 6: FAILED_VALIDATION, 3: COMPLETED
        job = wait_for_job_state(job_name, [7, 6, 3], [5, 1, 2])
        print(f"Job state after validation: {job.state}")
        
        if job.state in [4, 6]: # FAILED or FAILED_VALIDATION
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
             return f"Validation failed with state {job.state}. Errors: {'; '.join(error_msgs[:10])}{'...' if len(error_msgs) > 10 else ''}"
             
        # Assuming 7 is READY
        if job.state not in [7, 3]: # 7 is READY, 3 is COMPLETED
             return f"Validation failed or job not ready. State: {job.state}"
    except Exception as e:
        return f"Validation failed: {e}"

    print(f"Running import job {job_name}...")
    try:
        client.run_import_job(name=job_name)
        print("Waiting for import job to complete (polling state)...")
        # 2: RUNNING, 3: COMPLETED, 4: FAILED
        job = wait_for_job_state(job_name, [3, 4], [2, 1])
        print(f"Job state after run: {job.state}")
        if job.state != 3: # 3 is COMPLETED
            report = job.execution_report
            error_msgs = []
            if report and report.execution_errors:
                for err in report.execution_errors:
                    error_msgs.append(f"{err.error_details}")
            return f"Run failed. State: {job.state}. Errors: {'; '.join(error_msgs[:10])}"
    except Exception as e:
        return f"Run failed: {e}"

    return f"Successfully imported and processed data in job {job_name}. Uploaded: {uploaded_files}"
