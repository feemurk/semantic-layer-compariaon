-- Q-W-C1-D1 Stock group with the highest FY2015 share; each of its items' share of the group's FY2015 revenue.
WITH g AS (
  SELECT stock_group, MEASURE(revenue) AS group_revenue
  FROM slc.semantic.wwi_sales_by_stock_group WHERE fiscal_year = 2015 GROUP BY stock_group
),
top_group AS (SELECT stock_group, group_revenue FROM g ORDER BY group_revenue DESC, stock_group LIMIT 1),
items AS (
  SELECT stock_group, wwi_stock_item_id, stock_item, MEASURE(revenue) AS revenue
  FROM slc.semantic.wwi_sales_by_stock_group WHERE fiscal_year = 2015
  GROUP BY stock_group, wwi_stock_item_id, stock_item
)
SELECT t.stock_group AS stock_group_name, i.wwi_stock_item_id, i.stock_item, i.revenue,
       CAST(i.revenue AS DOUBLE) / CAST(t.group_revenue AS DOUBLE) AS share_of_group
FROM items i JOIN top_group t ON t.stock_group = i.stock_group
ORDER BY share_of_group DESC, i.wwi_stock_item_id
