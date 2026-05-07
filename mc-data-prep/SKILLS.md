# GCP Migration Center & Airlift Optimizer Skills

This tool provides capabilities to generate TCO reports and perform rightsizing assessments for migrating on-premises workloads to Google Cloud Platform.

## Usage Instructions

### 1. Manual VM Assessment
Perform a detailed rightsizing assessment for a single VM based on CPU benchmarks (Passmark) and utilization data.
```bash
python3 app/tco_report_generator.py assessment --cores 16 --ram 32 --disk 20 --passmark 750 --cpu-util 0.5 --disk-util 0.4 --target-series c4d
```

### 2. Airlift Quick Estimate
Perform a top-down, aggregated estimate for a large number of assets using industry-standard utilization defaults.
```bash
python3 app/tco_report_generator.py airlift --total-vcpus 1000 --total-ram 4000 --total-disk 10000
```

### 3. Migration Center TCO Report
Trigger automated TCO report generation in GCP Migration Center for pre-configured preference sets.
*Requires `.env` file with `GCP_PROJECT_ID`, `GCP_LOCATION`, etc.*
```bash
python3 app/tco_report_generator.py mc-report
```

### 4. Data Ingestion & Transformation
Transform raw VMware (RVTools) and Hyper-V exports into Migration Center CSV formats.
```bash
python3 app/data_transformer.py
```
*Note: This script iterates through `data/exports/` and outputs to `data/output/`.*

## Implementation Logic
The rightsizing engine uses:
- **Vapor Geomean Benchmarks:** Performance ratios for each GCE machine series.
- **CPU Rightsizing:** Adjusts core counts based on source utilization and target (default 75%).
- **Disk Rightsizing:** Adjusts capacity with a 25% uplift for headroom.
- **Airlift Defaults:** 22.7% CPU utilization, 35.7% RAM utilization, and 39% Disk utilization (based on analysis of 265k VMs).
