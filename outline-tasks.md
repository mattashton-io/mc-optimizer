# Migration Center Data Prep & Reporting Tasks

This roadmap tracks the tasks defined for the end-to-end Migration Center workflow, from initial data ingestion to the final reporting and discount analysis.

## Tasks

- [ ] **1. Data Ingestion & Wrangling (Agent 1: Ingestion/Wrangling)**
  - [ ] Collect customer server files.
  - [ ] Identify and validate necessary fields in the customer data.
  - [ ] Perform unit conversions (e.g., standardizing units like GB/TB/MB).
  - [ ] Run a data integrity check (95-99% confidence level) to ensure the imported data accurately reflects original customer documents.

- [ ] **2. Asset Migration & Management**
  - [ ] Import data into the Migration Center.
  - [ ] Manage assets (current approach avoids grouping/slicing for initial phases to keep reporting straightforward).

- [ ] **3. Report Generation & Comparison (Agent 2: Reporting/Right-Sizing)**
  - [ ] Combine asset data with standardized migration preferences (e.g., 23-36% and 40% benchmarks).
  - [ ] Generate comparative TCO and Licensing reports.
  - [ ] Provide cost options for one-year vs. three-year committed use discounts.
  - [ ] Generate "like-for-like" comparison (as-is vs. right-sized) to demonstrate the cost-effectiveness of right-sizing for Google Cloud.

- [ ] **4. Discount & Credit Analysis (Agent 3: Financial/Licensing)**
  - [ ] Extract Windows server data from the licensing report (identifying post-2019 servers eligible for PAYGO offsets).
  - [ ] Calculate potential offset credits for Windows licensing.
  - [ ] Apply logic for one-year deals (100% license coverage via credits).
  - [ ] Apply logic for three-year deals (100% coverage for first 24 months; 50% discount for the third year).
