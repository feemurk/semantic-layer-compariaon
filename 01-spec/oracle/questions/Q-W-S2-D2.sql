-- Q-W-S2-D2 For the month found in Q-W-S2-D1: ordered quantity by picker (Picker role of dim_employee; unknown member kept).
WITH oq AS (
  SELECT d.month_start_date, SUM(o.quantity) AS ordered_quantity
  FROM wwi.fact_order o JOIN wwi.dim_date d ON d.date_key = o.order_date
  WHERE d.calendar_year = 2015 GROUP BY d.month_start_date
),
us AS (
  SELECT d.month_start_date, SUM(f.quantity) AS units_sold
  FROM wwi.fact_sale f JOIN wwi.dim_date d ON d.date_key = f.invoice_date
  WHERE d.calendar_year = 2015 GROUP BY d.month_start_date
),
gap_month AS (
  SELECT oq.month_start_date
  FROM oq JOIN us ON us.month_start_date = oq.month_start_date
  ORDER BY ABS(oq.ordered_quantity - us.units_sold) DESC, oq.month_start_date
  LIMIT 1
)
SELECT g.month_start_date, p.employee AS picker, SUM(o.quantity) AS ordered_quantity
FROM wwi.fact_order o
JOIN wwi.dim_date d ON d.date_key = o.order_date
JOIN gap_month g ON g.month_start_date = d.month_start_date
LEFT JOIN wwi.dim_employee p ON p.employee_key = o.picker_key
GROUP BY g.month_start_date, p.employee
ORDER BY ordered_quantity DESC, picker NULLS FIRST
