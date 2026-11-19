-- Q-W-C2-D2 The 10 stock items with the lowest days of supply at 2015-12-31, excluding items with no sales in [t - 90, t] (ties: item id).
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
oh AS (
  SELECT wwi_stock_item_id, stock_item, SUM(quantity_on_hand) AS closing_units
  FROM snap WHERE snapshot_date = DATE '2015-12-31' GROUP BY wwi_stock_item_id, stock_item
),
u AS (
  SELECT wwi_stock_item_id, SUM(qty) AS units_sold_91d
  FROM sold WHERE invoice_date BETWEEN DATE '2015-12-31' - INTERVAL '90' DAY AND DATE '2015-12-31'
  GROUP BY wwi_stock_item_id
),
dos AS (
  SELECT oh.wwi_stock_item_id, oh.stock_item, oh.closing_units, u.units_sold_91d,
         CAST(oh.closing_units AS DOUBLE) / (CAST(u.units_sold_91d AS DOUBLE) / 91) AS days_of_supply
  FROM oh JOIN u ON u.wwi_stock_item_id = oh.wwi_stock_item_id
  WHERE u.units_sold_91d > 0
),
ranked AS (SELECT dos.*, ROW_NUMBER() OVER (ORDER BY days_of_supply, wwi_stock_item_id) AS rank_no FROM dos)
SELECT rank_no, wwi_stock_item_id, stock_item, closing_units, units_sold_91d, days_of_supply
FROM ranked WHERE rank_no <= 10
ORDER BY rank_no
