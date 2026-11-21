-- DSV named query nyc_date: database dimension NYC Date, role-played as Pickup Date and Dropoff Date.
-- stly_date_id is the same date one year earlier with 29 February mapped to 28 February (N-C1), NULL when the
-- prior year precedes the calendar; in_source_window marks the pickup source window 2023-2024 (SPEC § 5.2).
SELECT
  YEAR(d.date_key) * 10000 + MONTH(d.date_key) * 100 + DAY(d.date_key) AS date_id,
  CAST(d.date_key AS CHAR(10)) AS date_name,
  YEAR(d.date_key) * 100 + MONTH(d.date_key) AS month_id,
  CAST(d.month_start_date AS CHAR(10)) AS month_name,
  CAST((SELECT MAX(e.date_key) FROM nyctaxi.dim_date e WHERE e.month_start_date = d.month_start_date) AS CHAR(10))
    AS month_end_name,
  d.calendar_month AS month_of_year,
  CAST(d.calendar_month AS VARCHAR(2)) AS month_of_year_name,
  CAST(d.calendar_year AS INTEGER) * 10 + d.calendar_quarter AS quarter_id,
  CAST((SELECT MIN(e.date_key) FROM nyctaxi.dim_date e
        WHERE e.calendar_year = d.calendar_year AND e.calendar_quarter = d.calendar_quarter) AS CHAR(10))
    AS quarter_name,
  d.calendar_year,
  CAST(d.calendar_year AS VARCHAR(4)) AS calendar_year_name,
  d.day_of_week,
  CAST(d.day_of_week AS VARCHAR(1)) AS day_of_week_name,
  d.day_name,
  d.day_of_month,
  CAST(d.day_of_month AS VARCHAR(2)) AS day_of_month_name,
  d.day_of_year,
  CAST(d.day_of_year AS VARCHAR(3)) AS day_of_year_name,
  CASE
    WHEN d.calendar_year - 1 < (SELECT MIN(e.calendar_year) FROM nyctaxi.dim_date e) THEN NULL
    WHEN d.calendar_month = 2 AND d.day_of_month = 29 THEN (CAST(d.calendar_year AS INTEGER) - 1) * 10000 + 228
    ELSE (CAST(d.calendar_year AS INTEGER) - 1) * 10000 + CAST(d.calendar_month AS INTEGER) * 100 + d.day_of_month
  END AS stly_date_id,
  CAST(CASE
    WHEN d.calendar_year - 1 < (SELECT MIN(e.calendar_year) FROM nyctaxi.dim_date e) THEN NULL
    WHEN d.calendar_month = 2 AND d.day_of_month = 29 THEN (CAST(d.calendar_year AS INTEGER) - 1) * 10000 + 228
    ELSE (CAST(d.calendar_year AS INTEGER) - 1) * 10000 + CAST(d.calendar_month AS INTEGER) * 100 + d.day_of_month
  END AS VARCHAR(8)) AS stly_date_id_name,
  CASE WHEN d.calendar_year BETWEEN 2023 AND 2024 THEN 1 ELSE 0 END AS in_source_window,
  CASE WHEN d.calendar_year BETWEEN 2023 AND 2024 THEN 'true' ELSE 'false' END AS in_source_window_name
FROM nyctaxi.dim_date d
