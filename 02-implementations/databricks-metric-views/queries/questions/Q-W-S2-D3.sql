-- Q-W-S2-D3 Ordered quantity by selling package by calendar quarter, 2014 vs 2015.
WITH q AS (
  SELECT selling_package, calendar_quarter, calendar_year, MEASURE(ordered_quantity) AS ordered_quantity
  FROM slc.semantic.wwi_orders WHERE calendar_year IN (2014, 2015)
  GROUP BY selling_package, calendar_quarter, calendar_year
)
SELECT selling_package, calendar_quarter,
       SUM(CASE WHEN calendar_year = 2014 THEN ordered_quantity END) AS ordered_quantity_2014,
       SUM(CASE WHEN calendar_year = 2015 THEN ordered_quantity END) AS ordered_quantity_2015,
       CAST(SUM(CASE WHEN calendar_year = 2015 THEN ordered_quantity END) AS DOUBLE)
         / NULLIF(CAST(SUM(CASE WHEN calendar_year = 2014 THEN ordered_quantity END) AS DOUBLE), 0) - 1 AS change_pct
FROM q
GROUP BY selling_package, calendar_quarter
ORDER BY selling_package, calendar_quarter
