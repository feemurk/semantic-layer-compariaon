-- Q-W-M2-P Closing stock on hand (units) at each fiscal month end of FY2015: d* = last snapshot date of the fiscal month.
WITH ends AS (
  SELECT d.fiscal_month, MAX(h.snapshot_date) AS d_star
  FROM wwi.fact_stock_holding_daily h JOIN wwi.dim_date d ON d.date_key = h.snapshot_date
  WHERE d.fiscal_year = 2015 GROUP BY d.fiscal_month
)
SELECT e.fiscal_month, e.d_star AS month_end_date, SUM(h.quantity_on_hand) AS closing_units
FROM ends e JOIN wwi.fact_stock_holding_daily h ON h.snapshot_date = e.d_star
GROUP BY e.fiscal_month, e.d_star
ORDER BY e.fiscal_month
