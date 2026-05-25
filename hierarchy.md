Draft end-to-end workflow for Migration Center, from initial data ingestion to the final reporting and discount analysis:

**Workflow: Migration Center Data Prep & Reporting**

  * **Data Ingestion & Wrangling (Agent 1: Ingestion/Wrangling):**
      * Collect customer server files.
      * Identify and validate necessary fields in the customer data.
      * Perform unit conversions (e.g., standardizing units like GB/TB/MB).
      * Run a data integrity check (95-99% confidence level) to ensure the imported data accurately reflects original customer documents.
  * **Asset Migration & Management:**
      * Import data into the Migration Center.
      * Manage assets (current approach avoids grouping/slicing for initial phases to keep reporting straightforward).
  * **Report Generation & Comparison (Agent 2: Reporting/Right-Sizing):**
      * Combine asset data with standardized migration preferences (e.g., 23-36% and 40% benchmarks).
      * Generate comparative reports (TCO and Licensing).
      * Provide cost options for one-year vs. three-year committed use discounts.
      * Generate "like-for-like" comparison (as-is vs. right-sized) to demonstrate the cost-effectiveness of right-sizing for Google Cloud.
  * **Discount & Credit Analysis (Agent 3: Financial/Licensing):**
      * Extract Windows server data from the licensing report (identifying post-2019 servers eligible for PAYGO offsets).
      * Calculate potential offset credits for Windows licensing.
      * Apply logic for one-year deals (100% license coverage via credits).
      * Apply logic for three-year deals (100% coverage for first 24 months; 50% discount for the third year).
