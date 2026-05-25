# Migration Center Data Prep & Reporting Tasks

This roadmap tracks the tasks defined for the end-to-end Migration Center workflow, from initial data ingestion to the final reporting and discount analysis.

## Tasks
### TODOs
- [ ] **2. Asset Migration & Management (Programmatic API Auto-Import)**
  - [x] **Configure API Client & Authentication:** Initialize the `google-cloud-migrationcenter` Python client SDK using standard Application Default Credentials (ADC).
  - [x] **Generate Import Job:** Programmatically request the creation of a unique `CreateImportJobRequest` inside the target GCP project and location.
  - [x] **Acquire Signed URLs:** Call `CreateImportDataFileRequest` to register `vmInfo.csv` and `diskInfo.csv`, obtaining secure GCS upload endpoints.
  - [x] **Automate Binary Uploads:** Issue programmatic HTTP `PUT` requests to stream local CSVs to the generated signed URLs.
  - [x] **Trigger API Validation & Import Execution:** Invoke the API `Validate` and `Run` methods on the job and poll the long-running operation (LRO) until state transitions to successfully completed.
  - [ ] **Manage Assets:** Verify imported assets programmatically (avoiding initial grouping/slicing to keep reports straightforward).

### Future TODOs
