-- DSV named query wwi_date: database dimension Date (WWI calendar and fiscal attributes, SPEC § 5.4).
-- Integer keys (yyyymmdd, yyyymm, yyyyq) and ISO-text names so member captions equal the oracle's labels.
SELECT
  YEAR(d.date_key) * 10000 + MONTH(d.date_key) * 100 + DAY(d.date_key) AS date_id,
  CAST(d.date_key AS CHAR(10)) AS date_name,
  YEAR(d.date_key) * 100 + MONTH(d.date_key) AS month_id,
  CAST(d.month_start_date AS CHAR(10)) AS month_name,
  CAST((SELECT MAX(e.date_key) FROM wwi.dim_date e WHERE e.month_start_date = d.month_start_date) AS CHAR(10))
    AS month_end_name,
  d.calendar_month AS month_of_year,
  CAST(d.calendar_month AS VARCHAR(2)) AS month_of_year_name,
  CAST(d.calendar_year AS INTEGER) * 10 + d.calendar_quarter AS quarter_id,
  CONCAT(CAST(d.calendar_year AS VARCHAR(4)), ' Q', CAST(d.calendar_quarter AS VARCHAR(1))) AS quarter_name,
  CAST((SELECT MAX(e.date_key) FROM wwi.dim_date e
        WHERE e.calendar_year = d.calendar_year AND e.calendar_quarter = d.calendar_quarter) AS CHAR(10))
    AS quarter_end_name,
  d.calendar_quarter AS quarter_of_year,
  CAST(d.calendar_quarter AS VARCHAR(1)) AS quarter_of_year_name,
  d.calendar_year,
  CAST(d.calendar_year AS VARCHAR(4)) AS calendar_year_name,
  d.fiscal_period_index AS fiscal_month_id,
  CONCAT('FY', CAST(d.fiscal_year AS VARCHAR(4)), ' M', CAST(d.fiscal_month AS VARCHAR(2))) AS fiscal_month_name,
  d.fiscal_month AS fiscal_month_of_year,
  CAST(d.fiscal_month AS VARCHAR(2)) AS fiscal_month_of_year_name,
  CAST(d.fiscal_year AS INTEGER) * 10 + d.fiscal_quarter AS fiscal_quarter_id,
  CONCAT('FY', CAST(d.fiscal_year AS VARCHAR(4)), ' Q', CAST(d.fiscal_quarter AS VARCHAR(1))) AS fiscal_quarter_name,
  d.fiscal_quarter AS fiscal_quarter_of_year,
  CAST(d.fiscal_quarter AS VARCHAR(1)) AS fiscal_quarter_of_year_name,
  d.fiscal_year,
  CAST(d.fiscal_year AS VARCHAR(4)) AS fiscal_year_name
FROM wwi.dim_date d
