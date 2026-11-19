-- Q-W-C1-D3 Stock group shares FY2014 vs FY2015 and change in share points; is_top_gainer marks the largest gain (ties: name).
WITH fy AS (
  SELECT f.total_excluding_tax AS revenue, d.fiscal_year, si.wwi_stock_item_id
  FROM wwi.fact_sale f
  JOIN wwi.dim_date d ON d.date_key = f.invoice_date
  JOIN wwi.dim_stock_item si ON si.stock_item_key = f.stock_item_key
  WHERE d.fiscal_year IN (2014, 2015)
),
totals AS (SELECT fiscal_year, SUM(revenue) AS rev FROM fy GROUP BY fiscal_year),
shares AS (
  SELECT g.stock_group_name, fy.fiscal_year, CAST(SUM(fy.revenue) AS DOUBLE) / CAST(MAX(t.rev) AS DOUBLE) AS share
  FROM fy
  JOIN wwi.bridge_stock_item_group b ON b.wwi_stock_item_id = fy.wwi_stock_item_id
  JOIN wwi.dim_stock_group g ON g.stock_group_id = b.stock_group_id
  JOIN totals t ON t.fiscal_year = fy.fiscal_year
  GROUP BY g.stock_group_name, fy.fiscal_year
),
cmp AS (
  SELECT a.stock_group_name, a.share AS share_fy2014, b.share AS share_fy2015, (b.share - a.share) * 100 AS change_points
  FROM shares a JOIN shares b ON b.stock_group_name = a.stock_group_name AND b.fiscal_year = 2015
  WHERE a.fiscal_year = 2014
),
top_gainer AS (SELECT stock_group_name FROM cmp ORDER BY change_points DESC, stock_group_name LIMIT 1)
SELECT c.stock_group_name, c.share_fy2014, c.share_fy2015, c.change_points, c.stock_group_name = t.stock_group_name AS is_top_gainer
FROM cmp c CROSS JOIN top_gainer t
ORDER BY c.stock_group_name
