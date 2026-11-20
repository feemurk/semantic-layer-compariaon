-- Q-W-M2-P Closing stock at each fiscal month end of FY2015 (semi-additive closing_units, last snapshot of the month).
SELECT CAST(MONTH(snapshot_month) + 2 - CASE WHEN MONTH(snapshot_month) >= 11 THEN 12 ELSE 0 END AS INT) AS fiscal_month,
       LAST_DAY(snapshot_month) AS month_end_date, MEASURE(closing_units) AS closing_units
FROM slc.semantic.wwi_stock
WHERE snapshot_fiscal_year = 2015
GROUP BY snapshot_month
ORDER BY fiscal_month
