-- Q-W-M2-D2 Stock group with the most units at FY2015 end; its 10 items with the highest closing stock.
WITH g AS (
  SELECT stock_group, MEASURE(closing_units) AS units
  FROM slc.semantic.wwi_stock_by_stock_group WHERE snapshot_date = DATE '2015-10-31' GROUP BY stock_group
),
top_group AS (SELECT stock_group FROM g ORDER BY units DESC, stock_group LIMIT 1),
items AS (
  SELECT stock_group, wwi_stock_item_id, stock_item, MEASURE(closing_units) AS closing_units
  FROM slc.semantic.wwi_stock_by_stock_group WHERE snapshot_date = DATE '2015-10-31'
  GROUP BY stock_group, wwi_stock_item_id, stock_item
),
ranked AS (
  SELECT i.*, ROW_NUMBER() OVER (ORDER BY i.closing_units DESC, i.wwi_stock_item_id) AS rank_no
  FROM items i JOIN top_group t ON t.stock_group = i.stock_group
)
SELECT stock_group AS stock_group_name, rank_no, wwi_stock_item_id, stock_item, closing_units
FROM ranked WHERE rank_no <= 10
ORDER BY rank_no
