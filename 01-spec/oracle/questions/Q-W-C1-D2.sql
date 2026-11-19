-- Q-W-C1-D2 FY2015 stock group revenue share within each Sales Territory (denominator: the territory's deduplicated FY2015 revenue).
WITH fy AS (
  SELECT f.total_excluding_tax AS revenue, ci.sales_territory, si.wwi_stock_item_id
  FROM wwi.fact_sale f
  JOIN wwi.dim_date d ON d.date_key = f.invoice_date
  JOIN wwi.dim_city ci ON ci.city_key = f.city_key
  JOIN wwi.dim_stock_item si ON si.stock_item_key = f.stock_item_key
  WHERE d.fiscal_year = 2015
),
territory AS (SELECT sales_territory, SUM(revenue) AS rev FROM fy GROUP BY sales_territory)
SELECT fy.sales_territory, g.stock_group_name, SUM(fy.revenue) AS revenue,
       CAST(SUM(fy.revenue) AS DOUBLE) / CAST(t.rev AS DOUBLE) AS share_of_territory
FROM fy
JOIN wwi.bridge_stock_item_group b ON b.wwi_stock_item_id = fy.wwi_stock_item_id
JOIN wwi.dim_stock_group g ON g.stock_group_id = b.stock_group_id
JOIN territory t ON t.sales_territory = fy.sales_territory
GROUP BY fy.sales_territory, g.stock_group_name, t.rev
ORDER BY fy.sales_territory, g.stock_group_name
