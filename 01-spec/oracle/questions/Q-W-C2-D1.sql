-- Q-W-C2-D1 Days of supply at 2015-12-31 by stock group (items of each group via the bridge).
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
members AS (
  SELECT b.wwi_stock_item_id, g.stock_group_name
  FROM wwi.bridge_stock_item_group b JOIN wwi.dim_stock_group g ON g.stock_group_id = b.stock_group_id
),
oh AS (
  SELECT m.stock_group_name, SUM(s.quantity_on_hand) AS closing_units
  FROM snap s JOIN members m ON m.wwi_stock_item_id = s.wwi_stock_item_id
  WHERE s.snapshot_date = DATE '2015-12-31' GROUP BY m.stock_group_name
),
u AS (
  SELECT m.stock_group_name, SUM(x.qty) AS units_sold_91d
  FROM sold x JOIN members m ON m.wwi_stock_item_id = x.wwi_stock_item_id
  WHERE x.invoice_date BETWEEN DATE '2015-12-31' - INTERVAL '90' DAY AND DATE '2015-12-31'
  GROUP BY m.stock_group_name
)
SELECT oh.stock_group_name, oh.closing_units, u.units_sold_91d,
       CAST(oh.closing_units AS DOUBLE) / NULLIF(CAST(u.units_sold_91d AS DOUBLE) / 91, 0) AS days_of_supply
FROM oh LEFT JOIN u ON u.stock_group_name = oh.stock_group_name
ORDER BY oh.stock_group_name
