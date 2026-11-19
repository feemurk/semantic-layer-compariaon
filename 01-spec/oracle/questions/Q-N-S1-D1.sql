-- Q-N-S1-D1 The 2024 month with the highest gross trip revenue; the 15 Manhattan pickup zones with the most revenue that month (ties: location id).
WITH top_month AS (
  SELECT d.month_start_date
  FROM nyctaxi.fact_trip f JOIN nyctaxi.dim_date d ON d.date_key = f.pickup_date
  WHERE d.calendar_year = 2024
  GROUP BY d.month_start_date ORDER BY SUM(f.total_amount) DESC, d.month_start_date LIMIT 1
),
zones AS (
  SELECT t.month_start_date, f.pu_location_id, pz.zone, SUM(f.total_amount) AS revenue
  FROM nyctaxi.fact_trip f
  JOIN nyctaxi.dim_date d ON d.date_key = f.pickup_date
  JOIN top_month t ON t.month_start_date = d.month_start_date
  JOIN nyctaxi.dim_zone pz ON pz.location_id = f.pu_location_id
  WHERE pz.borough = 'Manhattan'
  GROUP BY t.month_start_date, f.pu_location_id, pz.zone
),
ranked AS (SELECT zones.*, ROW_NUMBER() OVER (ORDER BY revenue DESC, pu_location_id) AS rank_no FROM zones)
SELECT month_start_date, rank_no, pu_location_id, zone, revenue FROM ranked WHERE rank_no <= 15
ORDER BY rank_no
