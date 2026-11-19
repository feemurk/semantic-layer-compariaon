-- Q-W-M2-D4 The 10 stock items with the lowest closing stock at any calendar month end of 2015: each item's minimum month-end
-- closing units and the first month end at which it occurred (ties: units, then item id).
WITH ends AS (
  SELECT d.month_start_date, MAX(h.snapshot_date) AS d_star
  FROM wwi.fact_stock_holding_daily h JOIN wwi.dim_date d ON d.date_key = h.snapshot_date
  WHERE d.calendar_year = 2015 GROUP BY d.month_start_date
),
month_end AS (
  SELECT h.wwi_stock_item_id, e.d_star, h.quantity_on_hand, h.balance_basis
  FROM ends e JOIN wwi.fact_stock_holding_daily h ON h.snapshot_date = e.d_star
),
item_min AS (
  SELECT wwi_stock_item_id, MIN(quantity_on_hand) AS min_closing_units FROM month_end GROUP BY wwi_stock_item_id
),
first_at_min AS (
  SELECT m.wwi_stock_item_id, m.min_closing_units, MIN(x.d_star) AS month_end_date, MAX(x.balance_basis) AS balance_basis
  FROM item_min m
  JOIN month_end x ON x.wwi_stock_item_id = m.wwi_stock_item_id AND x.quantity_on_hand = m.min_closing_units
  GROUP BY m.wwi_stock_item_id, m.min_closing_units
),
ranked AS (
  SELECT f.*, ROW_NUMBER() OVER (ORDER BY f.min_closing_units, f.wwi_stock_item_id) AS rank_no FROM first_at_min f
)
SELECT r.rank_no, r.wwi_stock_item_id, si.stock_item, r.min_closing_units, r.month_end_date, r.balance_basis
FROM ranked r
JOIN wwi.dim_stock_item si ON si.wwi_stock_item_id = r.wwi_stock_item_id AND si.is_current
WHERE r.rank_no <= 10
ORDER BY r.rank_no
