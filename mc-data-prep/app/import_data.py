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
    OUTPUT_DIR = "data/output"
    
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
    import_job = {
        "display_name": f"Manual Import {time.strftime('%Y%m%d-%H%M%S')}"
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

    files = ["vmInfo.csv", "diskInfo.csv"]
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
    return f"Successfully imported data to job {job_name}. Uploaded: {uploaded_files}"
