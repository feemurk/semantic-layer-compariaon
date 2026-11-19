-- Q-W-C1-D4 FY2015: sum of stock group revenues, deduplicated total revenue, overlap (sum - total), and the overlap computed
-- directly from items in k >= 2 groups as sum((k - 1) * revenue); the two overlap columns must agree.
WITH fy AS (
  SELECT f.total_excluding_tax AS revenue, si.wwi_stock_item_id
  FROM wwi.fact_sale f
  JOIN wwi.dim_date d ON d.date_key = f.invoice_date
  JOIN wwi.dim_stock_item si ON si.stock_item_key = f.stock_item_key
  WHERE d.fiscal_year = 2015
),
k AS (SELECT wwi_stock_item_id, COUNT(*) AS groups FROM wwi.bridge_stock_item_group GROUP BY wwi_stock_item_id),
item_rev AS (SELECT wwi_stock_item_id, SUM(revenue) AS revenue FROM fy GROUP BY wwi_stock_item_id)
SELECT SUM(ir.revenue * COALESCE(k.groups, 0)) AS sum_of_group_revenue,
       SUM(ir.revenue) AS total_revenue,
       SUM(ir.revenue * COALESCE(k.groups, 0)) - SUM(ir.revenue) AS overlap_revenue,
       SUM(CASE WHEN k.groups >= 2 THEN ir.revenue * (k.groups - 1) ELSE 0 END) AS overlap_from_multi_group_items,
       SUM(CASE WHEN k.groups IS NULL THEN ir.revenue ELSE 0 END) AS revenue_without_group
FROM item_rev ir LEFT JOIN k ON k.wwi_stock_item_id = ir.wwi_stock_item_id
