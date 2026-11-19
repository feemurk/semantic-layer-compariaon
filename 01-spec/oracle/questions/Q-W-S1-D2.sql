-- Q-W-S1-D2 For the territory with the highest FY2015 revenue: the 10 stock items with the most FY2015 revenue,
-- each item's share of the territory's FY2015 revenue, and the combined share of the 10 (ties broken by item id).
WITH fy AS (
  SELECT f.total_excluding_tax AS revenue, ci.sales_territory, si.wwi_stock_item_id, si.stock_item
  FROM wwi.fact_sale f
  JOIN wwi.dim_date d ON d.date_key = f.invoice_date
  JOIN wwi.dim_city ci ON ci.city_key = f.city_key
  JOIN wwi.dim_stock_item si ON si.stock_item_key = f.stock_item_key
  WHERE d.fiscal_year = 2015
),
top_territory AS (
  SELECT sales_territory, SUM(revenue) AS territory_revenue FROM fy
  GROUP BY sales_territory ORDER BY SUM(revenue) DESC, sales_territory LIMIT 1
),
items AS (
  SELECT fy.wwi_stock_item_id, fy.stock_item, SUM(fy.revenue) AS revenue
  FROM fy JOIN top_territory t ON t.sales_territory = fy.sales_territory
  GROUP BY fy.wwi_stock_item_id, fy.stock_item
),
top10 AS (
  SELECT wwi_stock_item_id, stock_item, revenue,
         ROW_NUMBER() OVER (ORDER BY revenue DESC, wwi_stock_item_id) AS rank_no
  FROM items
)
SELECT t.sales_territory, x.rank_no, x.wwi_stock_item_id, x.stock_item, x.revenue,
       CAST(x.revenue AS DOUBLE) / CAST(t.territory_revenue AS DOUBLE) AS share_of_territory,
       CAST(SUM(x.revenue) OVER () AS DOUBLE) / CAST(t.territory_revenue AS DOUBLE) AS top10_combined_share
FROM top10 x CROSS JOIN top_territory t
WHERE x.rank_no <= 10
ORDER BY x.rank_no
