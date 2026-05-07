Here are the prompt instructions for the Gemini CLI to scaffold your Migration Center data import tool, based on the requirements discussed for cleaning customer exports and automating ingestion.

``` markdown
# Gemini Enterprise Migration Center Data Import Tool: CLI Prompt Instructions

Use the following prompts sequentially with the Gemini CLI to architect and implement the Migration Center data import tool.

## Prompt 1: Project Scaffolding & Architecture
"You are a Senior Cloud Engineer specializing in GCP Migration Center. I need a Python-based CLI application structure that accepts CSV or Excel files, maps them to the standard GCP Migration Center template format, and performs basic schema validation. Create a project skeleton with a modular architecture that separates file ingestion, data transformation logic, and logging."

## Prompt 2: Data Cleaning & Mapping Logic
"Implement a data transformation module for the application. The goal is to take 'messy' customer VM exports (which often have inconsistent headers and field naming conventions) and map them to the Migration Center template. 
- Use Pandas for tabular manipulation.
- Include logic to detect and suggest mappings for common fields (e.g., 'Memory' vs 'RAM', 'Storage' vs 'Disk').
- If fields are missing (e.g., specific disk performance metrics), flag them for 'industry assumption' application."

## Prompt 3: Human-in-the-Loop & Confidence Scoring
"Add a validation layer that integrates a Gemini model to review the mapped data.
- For every transformed row, calculate a 'Confidence Score' (0.0 to 1.0) based on how much data was inferred versus how much was explicitly mapped.
- Implement a 'Human-in-the-Loop' checkpoint: if the confidence score is below 0.8, the script must pause, present the row to the user in the CLI, highlight the ambiguity, and request manual confirmation or correction before proceeding.
- Ensure the user can approve or reject the suggested 'industry assumptions' for missing storage or disk data."

## Prompt 4: Migration Center API Integration (Placeholder)
"Create a function to export the validated, cleaned dataframe into the exact CSV format required by the GCP Migration Center. Include a 'Dry Run' mode that simulates the upload process and returns any API rejection errors before final submission."

```
