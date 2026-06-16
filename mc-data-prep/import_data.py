import os
import time
import google.auth
import requests
from google.cloud import migrationcenter_v1

# Paths
OUTPUT_DIR = "data/output"
LOCATION = "us-east4"  # Proposed location


def get_project_id():
    try:
        _, project_id = google.auth.default()
        return project_id
    except Exception as e:
        print(f"Failed to get project ID: {e}")
        return None


def create_import_job(client, project_id, location, job_id):
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
    operation = client.create_import_job(request=request)
    response = operation.result()
    print(f"Import job created: {response.name}")
    return response.name


def upload_file(client, job_name, file_path, file_name, file_format):
    parent = job_name

    # We need to use the correct enum or string for format.
    # Trying IMPORT_JOB_FORMAT_STRATOZONE_CSV as a guess.
    import_data_file = {"format": file_format}

    request = migrationcenter_v1.CreateImportDataFileRequest(
        parent=parent,
        import_data_file_id=file_name.replace(".", "-").lower(),
        import_data_file=import_data_file,
    )

    print(f"Creating import data file resource for {file_name}...")
    try:
        operation = client.create_import_data_file(request=request)
        response = operation.result()
        print(f"Import data file resource created: {response.name}")

        upload_uri = response.upload_file_info.signed_uri
        print(f"Uploading file to {upload_uri}...")

        with open(file_path, "rb") as f:
            resp = requests.put(
                upload_uri,
                data=f,
                headers={
                    "Content-Type": "application/octet-stream",
                    "x-goog-content-length-range": "0,104857600",
                },
            )
            if resp.status_code == 200:
                print(f"Successfully uploaded {file_name}")
            else:
                print(
                    f"Failed to upload {file_name}: {resp.status_code} - {resp.text}"
                )
    except Exception as e:
        print(f"Failed to create import data file for {file_name}: {e}")


def main():
    project_id = get_project_id()
    if not project_id:
        return

    print(f"Using project: {project_id}")

    client = migrationcenter_v1.MigrationCenterClient()

    job_id = f"manual-import-{int(time.time())}"
    job_name = create_import_job(client, project_id, LOCATION, job_id)

    # Files to upload
    files = ["vmInfo.csv", "diskInfo.csv"]

    for file_name in files:
        file_path = os.path.join(OUTPUT_DIR, file_name)
        if os.path.exists(file_path):
            upload_file(
                client,
                job_name,
                file_path,
                file_name,
                "IMPORT_JOB_FORMAT_STRATOZONE_CSV",
            )
        else:
            print(f"File not found: {file_path}")


if __name__ == "__main__":
    main()
