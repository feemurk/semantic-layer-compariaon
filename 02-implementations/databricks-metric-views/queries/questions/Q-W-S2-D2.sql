-- Q-W-S2-D2 For the Q-W-S2-D1 month: ordered quantity by picker (Picker role; unknown member kept).
WITH oq AS (
  SELECT month_start_date, MEASURE(ordered_quantity) AS ordered_quantity
  FROM slc.semantic.wwi_orders WHERE calendar_year = 2015 GROUP BY month_start_date
),
us AS (
  SELECT month_start_date, MEASURE(units_sold) AS units_sold
  FROM slc.semantic.wwi_sales WHERE calendar_year = 2015 GROUP BY month_start_date
),
gap_month AS (
  SELECT oq.month_start_date, oq.ordered_quantity, us.units_sold
  FROM oq JOIN us ON us.month_start_date = oq.month_start_date
  ORDER BY ABS(oq.ordered_quantity - us.units_sold) DESC, oq.month_start_date
  LIMIT 1
),
by_picker AS (
  SELECT month_start_date, picker, MEASURE(ordered_quantity) AS ordered_quantity
  FROM slc.semantic.wwi_orders WHERE calendar_year = 2015
  GROUP BY month_start_date, picker
)
SELECT g.month_start_date, b.picker, b.ordered_quantity
FROM by_picker b JOIN gap_month g ON g.month_start_date = b.month_start_date
ORDER BY b.ordered_quantity DESC, b.picker NULLS FIRST
