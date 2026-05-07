# Data Transformation Plan: Source to Migration Center (MC)

This document outlines the strategy for transforming raw VMware (RVTools) and Hyper-V exports into the standard Migration Center CSV formats (`vminfo.csv` and `diskinfo.csv`).

## 1. Safe Parsing with Pandas
We will use `pandas` to handle the ingestion of multiple CSV files.
- **Source Files:**
  - VMware: `vInfo.csv` (General VM info) and `vDisk.csv` (Disk details).
  - Hyper-V: `hvvmInfogcp.csv`.
- **Handling Multi-Source:** The agent will iterate through `data/exports/` and subdirectories, identifying source types based on column headers or file naming conventions.

## 2. Numeric Data Cleaning Strategy
To avoid `TypeError: unsupported operand type(s) for /: 'str' and 'int'`, we will implement a robust cleaning pipeline for all numeric columns (Cores, RAM, Disk Size).
- **Regex Cleaning:** All numeric columns will be stripped of commas and quotes before conversion.
- **Safe Conversion:**
  ```python
  def clean_numeric(val):
      if pd.isna(val): return 0
      return float(str(val).replace(',', '').replace('"', '').strip())
  ```
- **Vectorized Approach:** `df[col] = df[col].apply(clean_numeric)`

## 3. OS Normalization
Migration Center requires specific OS Type values (primarily 'Linux' or 'Windows').
- **Strategy:** Use keyword matching on `OS according to the configuration file` (VMware) or `OsName` (Hyper-V).
- **Mapping:**
  - `*Windows*` -> `Windows`
  - `*Linux*`, `*Ubuntu*`, `*Red Hat*`, `*CentOS*`, `*Debian*` -> `Linux`
  - Default to `Linux` for unknown but non-Windows systems to ensure valid import.

## 4. Synthetic MachineId Generation
Since source files may lack a consistent `MachineId` or even `MachineName` (in the case of some Hyper-V exports), we will generate synthetic IDs to link records.
- **Logic:**
  - **VMware:** Extract the VM name from the `Path` column (e.g., `campc1` from `.../campc1/campc1.vmx`).
  - **Linking:** Generate a deterministic UUID based on the VM Name or the `VI SDK UUID`.
  - **Format:** `iona-uuid-<short-hash>` (e.g., `iona-uuid-a1b2c3d4`).
- **Disk Linking:** A mapping dictionary `vm_name -> machine_id` will be maintained during the `vInfo` pass to ensure `vDisk` entries are correctly associated with their parent VMs.

## 5. Output Generation
The final step will be mapping the cleaned and normalized dataframes to the required MC templates:
- **vminfo.csv:** Mapping CPUs, RAM (converting MiB to GiB where necessary), and OS info.
- **diskinfo.csv:** Iterating through all disks associated with each `MachineId`.
