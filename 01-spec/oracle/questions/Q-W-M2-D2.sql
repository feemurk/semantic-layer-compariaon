-- Q-W-M2-D2 Stock group with the most units at FY2015 end (ties: name); its 10 stock items with the highest closing stock (ties: item id).
WITH snap AS (
  SELECT h.wwi_stock_item_id, h.quantity_on_hand, si.stock_item
  FROM wwi.fact_stock_holding_daily h
  JOIN wwi.dim_stock_item si ON si.stock_item_key = h.stock_item_key
  WHERE h.snapshot_date = DATE '2015-10-31'
),
grp AS (
  SELECT s.*, g.stock_group_name
  FROM snap s
  JOIN wwi.bridge_stock_item_group b ON b.wwi_stock_item_id = s.wwi_stock_item_id
  JOIN wwi.dim_stock_group g ON g.stock_group_id = b.stock_group_id
),
top_group AS (
  SELECT stock_group_name FROM grp GROUP BY stock_group_name ORDER BY SUM(quantity_on_hand) DESC, stock_group_name LIMIT 1
),
ranked AS (
  SELECT grp.stock_group_name, grp.wwi_stock_item_id, grp.stock_item, grp.quantity_on_hand,
         ROW_NUMBER() OVER (ORDER BY grp.quantity_on_hand DESC, grp.wwi_stock_item_id) AS rank_no
  FROM grp JOIN top_group t ON t.stock_group_name = grp.stock_group_name
)
SELECT stock_group_name, rank_no, wwi_stock_item_id, stock_item, quantity_on_hand AS closing_units
FROM ranked WHERE rank_no <= 10
ORDER BY rank_no
