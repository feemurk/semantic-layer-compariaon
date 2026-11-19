-- Q-W-S2-P Ordered quantity (by order_date) and revenue excl. tax (by invoice_date) per calendar month of 2015 on one shared date axis.
WITH months AS (
  SELECT DISTINCT month_start_date FROM wwi.dim_date WHERE calendar_year = 2015
),
oq AS (
  SELECT d.month_start_date, SUM(o.quantity) AS ordered_quantity
  FROM wwi.fact_order o JOIN wwi.dim_date d ON d.date_key = o.order_date
  WHERE d.calendar_year = 2015 GROUP BY d.month_start_date
),
rev AS (
  SELECT d.month_start_date, SUM(f.total_excluding_tax) AS revenue
  FROM wwi.fact_sale f JOIN wwi.dim_date d ON d.date_key = f.invoice_date
  WHERE d.calendar_year = 2015 GROUP BY d.month_start_date
)
SELECT m.month_start_date, oq.ordered_quantity, rev.revenue
FROM months m
LEFT JOIN oq ON oq.month_start_date = m.month_start_date
LEFT JOIN rev ON rev.month_start_date = m.month_start_date
ORDER BY m.month_start_date
