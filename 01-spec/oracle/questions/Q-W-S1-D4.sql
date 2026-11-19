-- Q-W-S1-D4 FY2015 revenue by stock item Color as recorded at time of sale (surrogate key, as-was) and by the item's
-- current Color (durable key -> is_current row, as-is); differs = true where the two attributions disagree.
WITH fy AS (
  SELECT f.total_excluding_tax AS revenue, si.color AS color_as_was, cur.color AS color_as_is
  FROM wwi.fact_sale f
  JOIN wwi.dim_date d ON d.date_key = f.invoice_date
  JOIN wwi.dim_stock_item si ON si.stock_item_key = f.stock_item_key
  JOIN wwi.dim_stock_item cur ON cur.wwi_stock_item_id = si.wwi_stock_item_id AND cur.is_current
  WHERE d.fiscal_year = 2015
),
was AS (SELECT color_as_was AS color, SUM(revenue) AS revenue FROM fy GROUP BY color_as_was),
iss AS (SELECT color_as_is AS color, SUM(revenue) AS revenue FROM fy GROUP BY color_as_is),
colors AS (SELECT color FROM was UNION SELECT color FROM iss)
SELECT c.color, w.revenue AS revenue_as_was, i.revenue AS revenue_as_is,
       COALESCE(w.revenue, 0) <> COALESCE(i.revenue, 0) AS differs
FROM colors c
LEFT JOIN was w ON w.color = c.color
LEFT JOIN iss i ON i.color = c.color
ORDER BY c.color
