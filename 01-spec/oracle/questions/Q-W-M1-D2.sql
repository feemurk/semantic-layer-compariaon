-- Q-W-M1-D2 For the 10 items of Q-W-M1-D1 (FY2015, lowest-margin customer category): gross margin % by Sales Territory.
WITH fy AS (
  SELECT f.total_excluding_tax AS revenue, f.profit, c.category, ci.sales_territory, si.wwi_stock_item_id, si.stock_item
  FROM wwi.fact_sale f
  JOIN wwi.dim_date d ON d.date_key = f.invoice_date
  JOIN wwi.dim_customer c ON c.customer_key = f.customer_key
  JOIN wwi.dim_city ci ON ci.city_key = f.city_key
  JOIN wwi.dim_stock_item si ON si.stock_item_key = f.stock_item_key
  WHERE d.fiscal_year = 2015
),
low_cat AS (
  SELECT category FROM fy GROUP BY category
  ORDER BY CAST(SUM(profit) AS DOUBLE) / NULLIF(CAST(SUM(revenue) AS DOUBLE), 0), category LIMIT 1
),
items AS (
  SELECT fy.wwi_stock_item_id,
         CAST(SUM(fy.profit) AS DOUBLE) / NULLIF(CAST(SUM(fy.revenue) AS DOUBLE), 0) AS gross_margin_pct
  FROM fy JOIN low_cat l ON l.category = fy.category
  GROUP BY fy.wwi_stock_item_id
  HAVING SUM(fy.revenue) > 10000
),
top10 AS (
  SELECT wwi_stock_item_id FROM items ORDER BY gross_margin_pct, wwi_stock_item_id LIMIT 10
)
SELECT fy.wwi_stock_item_id, fy.stock_item, fy.sales_territory, SUM(fy.revenue) AS revenue, SUM(fy.profit) AS profit,
       CAST(SUM(fy.profit) AS DOUBLE) / NULLIF(CAST(SUM(fy.revenue) AS DOUBLE), 0) AS gross_margin_pct
FROM fy
JOIN low_cat l ON l.category = fy.category
JOIN top10 t ON t.wwi_stock_item_id = fy.wwi_stock_item_id
GROUP BY fy.wwi_stock_item_id, fy.stock_item, fy.sales_territory
ORDER BY fy.wwi_stock_item_id, fy.sales_territory
