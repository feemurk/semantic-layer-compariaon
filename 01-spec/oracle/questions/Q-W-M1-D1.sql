-- Q-W-M1-D1 Customer category with the lowest FY2015 gross margin %; within it, the 10 stock items with the lowest FY2015
-- gross margin % among items with FY2015 revenue > 10,000 (ties broken by item id).
WITH fy AS (
  SELECT f.total_excluding_tax AS revenue, f.profit, c.category, si.wwi_stock_item_id, si.stock_item
  FROM wwi.fact_sale f
  JOIN wwi.dim_date d ON d.date_key = f.invoice_date
  JOIN wwi.dim_customer c ON c.customer_key = f.customer_key
  JOIN wwi.dim_stock_item si ON si.stock_item_key = f.stock_item_key
  WHERE d.fiscal_year = 2015
),
low_cat AS (
  SELECT category FROM fy GROUP BY category
  ORDER BY CAST(SUM(profit) AS DOUBLE) / NULLIF(CAST(SUM(revenue) AS DOUBLE), 0), category LIMIT 1
),
items AS (
  SELECT fy.category, fy.wwi_stock_item_id, fy.stock_item, SUM(fy.revenue) AS revenue, SUM(fy.profit) AS profit,
         CAST(SUM(fy.profit) AS DOUBLE) / NULLIF(CAST(SUM(fy.revenue) AS DOUBLE), 0) AS gross_margin_pct
  FROM fy JOIN low_cat l ON l.category = fy.category
  GROUP BY fy.category, fy.wwi_stock_item_id, fy.stock_item
  HAVING SUM(fy.revenue) > 10000
),
ranked AS (
  SELECT items.*, ROW_NUMBER() OVER (ORDER BY gross_margin_pct, wwi_stock_item_id) AS rank_no FROM items
)
SELECT category AS customer_category, rank_no, wwi_stock_item_id, stock_item, revenue, profit, gross_margin_pct
FROM ranked WHERE rank_no <= 10
ORDER BY rank_no
