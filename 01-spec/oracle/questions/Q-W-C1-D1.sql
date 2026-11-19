-- Q-W-C1-D1 Stock group with the highest FY2015 share (ties: name); each of its stock items' share of the group's FY2015 revenue.
WITH fy AS (
  SELECT f.total_excluding_tax AS revenue, si.wwi_stock_item_id, si.stock_item, g.stock_group_name
  FROM wwi.fact_sale f
  JOIN wwi.dim_date d ON d.date_key = f.invoice_date
  JOIN wwi.dim_stock_item si ON si.stock_item_key = f.stock_item_key
  JOIN wwi.bridge_stock_item_group b ON b.wwi_stock_item_id = si.wwi_stock_item_id
  JOIN wwi.dim_stock_group g ON g.stock_group_id = b.stock_group_id
  WHERE d.fiscal_year = 2015
),
top_group AS (
  SELECT stock_group_name, SUM(revenue) AS group_revenue FROM fy
  GROUP BY stock_group_name ORDER BY SUM(revenue) DESC, stock_group_name LIMIT 1
)
SELECT t.stock_group_name, fy.wwi_stock_item_id, fy.stock_item, SUM(fy.revenue) AS revenue,
       CAST(SUM(fy.revenue) AS DOUBLE) / CAST(t.group_revenue AS DOUBLE) AS share_of_group
FROM fy JOIN top_group t ON t.stock_group_name = fy.stock_group_name
GROUP BY t.stock_group_name, t.group_revenue, fy.wwi_stock_item_id, fy.stock_item
ORDER BY share_of_group DESC, fy.wwi_stock_item_id
