
# Data Mart Loading & Credit Rating Reporting - Project Deliverables

This folder contains processed outputs and templates generated from the notebook 'project_full_pipeline.ipynb'.

## Files generated
- data/processed/transactions_cleaned.csv : Cleaned transaction-level staging data
- data/processed/ratings_type2_sample.csv : Sample SCD Type-2 ratings table
- data/processed/rating_frequency_per_vendor_year.csv : KPI - rating change frequency
- data/processed/outlier_precision_by_security_date.csv : KPI - outlier percentage and precision
- reports/test_cases_template.csv : Test case template CSV
- reports/test_scenarios_template.csv : Test scenario template CSV
- deliverables_manifest.json : Manifest of generated deliverables

## How to use
1. Use ratings_type2_sample.csv to populate dimension/history tables in your data mart (SCD Type-2).
2. Use KPI CSVs as direct sources for Power BI / Tableau dashboards.

