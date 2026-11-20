-- Q-W-S1-D2 Top FY2015 territory: 10 stock items with the most revenue, item share and combined share of territory revenue.
WITH by_item AS (
  SELECT sales_territory, wwi_stock_item_id, stock_item, MEASURE(revenue) AS revenue
  FROM slc.semantic.wwi_sales
  WHERE fiscal_year = 2015
  GROUP BY sales_territory, wwi_stock_item_id, stock_item
),
territory AS (
  SELECT sales_territory, MEASURE(revenue) AS territory_revenue
  FROM slc.semantic.wwi_sales
  WHERE fiscal_year = 2015
  GROUP BY sales_territory
),
top_territory AS (
  SELECT sales_territory, territory_revenue FROM territory ORDER BY territory_revenue DESC, sales_territory LIMIT 1
),
top10 AS (
  SELECT b.wwi_stock_item_id, b.stock_item, b.revenue,
         ROW_NUMBER() OVER (ORDER BY b.revenue DESC, b.wwi_stock_item_id) AS rank_no
  FROM by_item b JOIN top_territory t ON t.sales_territory = b.sales_territory
)
SELECT t.sales_territory, x.rank_no, x.wwi_stock_item_id, x.stock_item, x.revenue,
       CAST(x.revenue AS DOUBLE) / CAST(t.territory_revenue AS DOUBLE) AS share_of_territory,
       CAST(SUM(x.revenue) OVER () AS DOUBLE) / CAST(t.territory_revenue AS DOUBLE) AS top10_combined_share
FROM top10 x CROSS JOIN top_territory t
WHERE x.rank_no <= 10
ORDER BY x.rank_no
