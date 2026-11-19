-- Q-W-C2-P Days of supply at each calendar month end of 2015, company-wide: t = month end; DOS = closing units / (units sold in [t - 90, t] / 91).
WITH snap AS (
  SELECT h.snapshot_date, h.quantity_on_hand, h.wwi_stock_item_id, si.stock_item, si.is_chiller_stock
  FROM wwi.fact_stock_holding_daily h
  JOIN wwi.dim_stock_item si ON si.stock_item_key = h.stock_item_key
),
sold AS (
  SELECT si.wwi_stock_item_id, f.invoice_date, SUM(f.quantity) AS qty
  FROM wwi.fact_sale f JOIN wwi.dim_stock_item si ON si.stock_item_key = f.stock_item_key
  GROUP BY si.wwi_stock_item_id, f.invoice_date
),
ends AS (
  SELECT d.month_start_date, MAX(s.snapshot_date) AS t
  FROM snap s JOIN wwi.dim_date d ON d.date_key = s.snapshot_date
  WHERE d.calendar_year = 2015 GROUP BY d.month_start_date
),
oh AS (SELECT e.t, SUM(s.quantity_on_hand) AS closing_units FROM ends e JOIN snap s ON s.snapshot_date = e.t GROUP BY e.t),
u AS (
  SELECT e.t, SUM(x.qty) AS units_sold_91d
  FROM ends e JOIN sold x ON x.invoice_date BETWEEN e.t - INTERVAL '90' DAY AND e.t
  GROUP BY e.t
)
SELECT oh.t AS month_end_date, oh.closing_units, u.units_sold_91d,
       CAST(oh.closing_units AS DOUBLE) / NULLIF(CAST(u.units_sold_91d AS DOUBLE) / 91, 0) AS days_of_supply
FROM oh LEFT JOIN u ON u.t = oh.t
ORDER BY oh.t
