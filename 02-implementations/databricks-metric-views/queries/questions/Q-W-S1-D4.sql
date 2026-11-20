-- Q-W-S1-D4 FY2015 revenue by stock item color as-was (field color) and as-is (field current_color, nested SCD2 join).
WITH was AS (
  SELECT color, MEASURE(revenue) AS revenue FROM slc.semantic.wwi_sales WHERE fiscal_year = 2015 GROUP BY color
),
iss AS (
  SELECT current_color AS color, MEASURE(revenue) AS revenue FROM slc.semantic.wwi_sales WHERE fiscal_year = 2015 GROUP BY current_color
),
colors AS (SELECT color FROM was UNION SELECT color FROM iss)
SELECT c.color, w.revenue AS revenue_as_was, i.revenue AS revenue_as_is,
       COALESCE(w.revenue, 0) <> COALESCE(i.revenue, 0) AS differs
FROM colors c
LEFT JOIN was w ON w.color = c.color
LEFT JOIN iss i ON i.color = c.color
ORDER BY c.color
