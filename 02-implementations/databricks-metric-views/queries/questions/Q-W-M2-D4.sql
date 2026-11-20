-- Q-W-M2-D4 The 10 items with the lowest closing stock at any 2015 calendar month end, and the first month end at that minimum.
WITH month_end AS (
  SELECT wwi_stock_item_id, snapshot_month, LAST_DAY(snapshot_month) AS month_end_date, balance_basis,
         MEASURE(closing_units) AS units
  FROM slc.semantic.wwi_stock WHERE YEAR(snapshot_month) = 2015
  GROUP BY wwi_stock_item_id, snapshot_month, balance_basis
),
item_min AS (SELECT wwi_stock_item_id, MIN(units) AS min_closing_units FROM month_end GROUP BY wwi_stock_item_id),
first_at_min AS (
  SELECT m.wwi_stock_item_id, m.min_closing_units, MIN(x.month_end_date) AS month_end_date, MAX(x.balance_basis) AS balance_basis
  FROM item_min m JOIN month_end x ON x.wwi_stock_item_id = m.wwi_stock_item_id AND x.units = m.min_closing_units
  GROUP BY m.wwi_stock_item_id, m.min_closing_units
),
names AS (
  SELECT wwi_stock_item_id, stock_item FROM slc.semantic.wwi_stock WHERE snapshot_date = DATE '2016-05-31'
  GROUP BY wwi_stock_item_id, stock_item
),
ranked AS (SELECT f.*, ROW_NUMBER() OVER (ORDER BY f.min_closing_units, f.wwi_stock_item_id) AS rank_no FROM first_at_min f)
SELECT r.rank_no, r.wwi_stock_item_id, n.stock_item, r.min_closing_units, r.month_end_date, r.balance_basis
FROM ranked r JOIN names n ON n.wwi_stock_item_id = r.wwi_stock_item_id
WHERE r.rank_no <= 10
ORDER BY r.rank_no
