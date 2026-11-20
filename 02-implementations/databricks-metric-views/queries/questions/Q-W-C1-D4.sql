-- Q-W-C1-D4 FY2015 sum of group revenues, deduplicated total, overlap, and overlap from items in two or more groups
-- (item group counts from the bridge view's revenue / deduplicated revenue per item).
WITH per_item AS (
  SELECT wwi_stock_item_id, MEASURE(revenue) AS group_revenue, MEASURE(revenue_deduplicated) AS revenue
  FROM slc.semantic.wwi_sales_by_stock_group WHERE fiscal_year = 2015 GROUP BY wwi_stock_item_id
),
total AS (SELECT MEASURE(revenue) AS revenue FROM slc.semantic.wwi_sales WHERE fiscal_year = 2015)
SELECT SUM(p.group_revenue) AS sum_of_group_revenue,
       MAX(t.revenue) AS total_revenue,
       SUM(p.group_revenue) - MAX(t.revenue) AS overlap_revenue,
       SUM(CASE WHEN p.group_revenue > p.revenue THEN p.group_revenue - p.revenue ELSE 0 END) AS overlap_from_multi_group_items,
       MAX(t.revenue) - SUM(p.revenue) AS revenue_without_group
FROM per_item p CROSS JOIN total t
