-- Q-N-S1-D1 2024 month with the highest revenue; the 15 Manhattan pickup zones with the most revenue that month.
WITH top_month AS (
  SELECT pickup_month FROM (
    SELECT pickup_month, MEASURE(gross_trip_revenue) AS revenue FROM slc.semantic.nyc_trips
    WHERE YEAR(pickup_month) = 2024 GROUP BY pickup_month
  ) m ORDER BY revenue DESC, pickup_month LIMIT 1
),
zones AS (
  SELECT pickup_month, pickup_zone_id, pickup_zone, MEASURE(gross_trip_revenue) AS revenue
  FROM slc.semantic.nyc_trips WHERE YEAR(pickup_month) = 2024 AND pickup_borough = 'Manhattan'
  GROUP BY pickup_month, pickup_zone_id, pickup_zone
),
ranked AS (
  SELECT z.*, ROW_NUMBER() OVER (ORDER BY z.revenue DESC, z.pickup_zone_id) AS rank_no
  FROM zones z JOIN top_month t ON t.pickup_month = z.pickup_month
)
SELECT pickup_month AS month_start_date, rank_no, pickup_zone_id AS pu_location_id, pickup_zone AS zone, revenue
FROM ranked WHERE rank_no <= 15
ORDER BY rank_no
