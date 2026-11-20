-- Q-W-M1-D1 Lowest-margin customer category (FY2015); its 10 lowest-margin items with FY2015 revenue > 10,000.
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
)
SELECT customer_category, rank_no, wwi_stock_item_id, stock_item, revenue, profit, gross_margin_pct
FROM ranked WHERE rank_no <= 10
ORDER BY rank_no
