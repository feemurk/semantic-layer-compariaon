-- Q-W-M1-D2 For the 10 items of Q-W-M1-D1: gross margin % by Sales Territory (FY2015, lowest-margin category).
WITH cat AS (
  SELECT customer_category, MEASURE(gross_margin_pct) AS gm FROM slc.semantic.wwi_sales WHERE fiscal_year = 2015 GROUP BY customer_category
),
low_cat AS (SELECT customer_category FROM cat ORDER BY gm, customer_category LIMIT 1),
items AS (
  SELECT customer_category, wwi_stock_item_id, stock_item, MEASURE(revenue) AS revenue, MEASURE(gross_profit) AS profit,
         MEASURE(gross_margin_pct) AS gross_margin_pct
  FROM slc.semantic.wwi_sales WHERE fiscal_year = 2015
  GROUP BY customer_category, wwi_stock_item_id, stock_item
),
ranked AS (
  SELECT i.*, ROW_NUMBER() OVER (ORDER BY i.gross_margin_pct, i.wwi_stock_item_id) AS rank_no
  FROM items i JOIN low_cat l ON l.customer_category = i.customer_category
  WHERE i.revenue > 10000
),
by_territory AS (
  SELECT customer_category, wwi_stock_item_id, stock_item, sales_territory, MEASURE(revenue) AS revenue,
         MEASURE(gross_profit) AS profit, MEASURE(gross_margin_pct) AS gross_margin_pct
  FROM slc.semantic.wwi_sales WHERE fiscal_year = 2015
  GROUP BY customer_category, wwi_stock_item_id, stock_item, sales_territory
)
SELECT b.wwi_stock_item_id, b.stock_item, b.sales_territory, b.revenue, b.profit, b.gross_margin_pct
FROM by_territory b
JOIN ranked r ON r.wwi_stock_item_id = b.wwi_stock_item_id AND r.customer_category = b.customer_category AND r.rank_no <= 10
ORDER BY b.wwi_stock_item_id, b.sales_territory
