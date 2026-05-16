# Snowflake apply order

1. `01_schema.sql` — tables + stream
2. `02_cortex_triage.sql` — Cortex severity triage task
3. `03_dynamic_tables.sql` — INCIDENT_CLUSTERS + RESOURCE_ROSTER + SEVERITY_HEATMAP_H3
4. `04_dispatch_proc.sql` — DISPATCH_INCIDENTS stored proc + DISPATCH_TASK
5. `05_udf_location.py` — Snowpark UDF for place-description fallback
6. `06_scenario_proc.sql` — optional; API owns v1 demo timing

After applying, run `SHOW DYNAMIC TABLES;` and confirm
`last_refresh_status = SUCCEEDED`.
