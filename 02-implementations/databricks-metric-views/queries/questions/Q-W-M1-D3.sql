-- Q-W-M1-D3 Gross margin % by selling package, FY2014 vs FY2015; change in percentage points.
WITH g AS (
  SELECT selling_package, fiscal_year, MEASURE(gross_margin_pct) AS gm
  FROM slc.semantic.wwi_sales WHERE fiscal_year IN (2014, 2015)
  GROUP BY selling_package, fiscal_year
)
SELECT selling_package,
       MAX(CASE WHEN fiscal_year = 2014 THEN gm END) AS gross_margin_pct_fy2014,
       MAX(CASE WHEN fiscal_year = 2015 THEN gm END) AS gross_margin_pct_fy2015,
       (MAX(CASE WHEN fiscal_year = 2015 THEN gm END) - MAX(CASE WHEN fiscal_year = 2014 THEN gm END)) * 100 AS change_points
FROM g
GROUP BY selling_package
ORDER BY selling_package
