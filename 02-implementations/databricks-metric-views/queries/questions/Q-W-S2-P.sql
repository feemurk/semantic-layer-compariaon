-- Q-W-S2-P Ordered quantity (wwi_orders, order date) and revenue (wwi_sales, invoice date) per 2015 month on one date axis.
WITH oq AS (
  SELECT month_start_date, MEASURE(ordered_quantity) AS ordered_quantity
  FROM slc.semantic.wwi_orders WHERE calendar_year = 2015 GROUP BY month_start_date
),
rev AS (
  SELECT month_start_date, MEASURE(revenue) AS revenue
  FROM slc.semantic.wwi_sales WHERE calendar_year = 2015 GROUP BY month_start_date
),
months AS (SELECT month_start_date FROM oq UNION SELECT month_start_date FROM rev)
SELECT m.month_start_date, oq.ordered_quantity, rev.revenue
FROM months m
LEFT JOIN oq ON oq.month_start_date = m.month_start_date
LEFT JOIN rev ON rev.month_start_date = m.month_start_date
ORDER BY m.month_start_date
