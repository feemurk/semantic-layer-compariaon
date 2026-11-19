-- Q-W-C2-D3 Days of supply for chiller vs non-chiller items at each calendar quarter end of 2015.
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
  SELECT d.calendar_quarter, MAX(s.snapshot_date) AS t
  FROM snap s JOIN wwi.dim_date d ON d.date_key = s.snapshot_date
  WHERE d.calendar_year = 2015 GROUP BY d.calendar_quarter
),
chill AS (SELECT DISTINCT wwi_stock_item_id, is_chiller_stock FROM snap),
oh AS (
  SELECT e.calendar_quarter, e.t, s.is_chiller_stock, SUM(s.quantity_on_hand) AS closing_units
  FROM ends e JOIN snap s ON s.snapshot_date = e.t
  GROUP BY e.calendar_quarter, e.t, s.is_chiller_stock
),
u AS (
  SELECT e.calendar_quarter, c.is_chiller_stock, SUM(x.qty) AS units_sold_91d
  FROM ends e
  JOIN sold x ON x.invoice_date BETWEEN e.t - INTERVAL '90' DAY AND e.t
  JOIN chill c ON c.wwi_stock_item_id = x.wwi_stock_item_id
  GROUP BY e.calendar_quarter, c.is_chiller_stock
)
SELECT oh.calendar_quarter, oh.t AS quarter_end_date, oh.is_chiller_stock, oh.closing_units, u.units_sold_91d,
       CAST(oh.closing_units AS DOUBLE) / NULLIF(CAST(u.units_sold_91d AS DOUBLE) / 91, 0) AS days_of_supply
FROM oh LEFT JOIN u ON u.calendar_quarter = oh.calendar_quarter AND u.is_chiller_stock = oh.is_chiller_stock
ORDER BY oh.calendar_quarter, oh.is_chiller_stock
