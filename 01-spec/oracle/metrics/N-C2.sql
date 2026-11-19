-- N-C2 MTD-to-YTD Daily Pace Index, trips counted by Pickup Date. t = last calendar day of the period, capped at 2024-12-31.
-- PACE = (TRIPS_MTD(t) / day_of_month(t)) / (TRIPS_YTD(t) / day_of_year(t)); denominators are calendar days elapsed, not days with trips.
-- NULL when YTD trips are absent; components :mtd_trips and :ytd_trips are NULL when no trip qualifies. Member grains as N-C1.
WITH daily_detail AS (
  SELECT f.pickup_date, pz.borough, pt.payment_type_name, f.vendor_id, f.pickup_hour,
         SUM(f.total_amount) AS revenue, COUNT(*) AS trips
  FROM nyctaxi.fact_trip f
  JOIN nyctaxi.dim_zone pz ON pz.location_id = f.pu_location_id
  JOIN nyctaxi.dim_payment_type pt ON pt.payment_type = f.payment_type
  GROUP BY f.pickup_date, pz.borough, pt.payment_type_name, f.vendor_id, f.pickup_hour
),
daily AS (
  SELECT 'all' AS dim, CAST(NULL AS STRING) AS member, pickup_date, SUM(revenue) AS revenue, SUM(trips) AS trips
  FROM daily_detail GROUP BY pickup_date
  UNION ALL SELECT 'pickup_borough', borough, pickup_date, SUM(revenue), SUM(trips) FROM daily_detail GROUP BY borough, pickup_date
  UNION ALL SELECT 'payment_type', payment_type_name, pickup_date, SUM(revenue), SUM(trips) FROM daily_detail GROUP BY payment_type_name, pickup_date
  UNION ALL SELECT 'vendor', CAST(vendor_id AS STRING), pickup_date, SUM(revenue), SUM(trips) FROM daily_detail GROUP BY vendor_id, pickup_date
  UNION ALL SELECT 'pickup_hour', CAST(pickup_hour AS STRING), pickup_date, SUM(revenue), SUM(trips) FROM daily_detail GROUP BY pickup_hour, pickup_date
),
members AS (SELECT DISTINCT dim, member FROM daily),
cal AS (
  SELECT date_key, calendar_year, month_start_date, day_of_month, day_of_year
  FROM nyctaxi.dim_date
  WHERE date_key BETWEEN DATE '2023-01-01' AND DATE '2024-12-31'
),
anchors AS (
  SELECT 'day' AS period, CAST(date_key AS STRING) AS period_member, date_key AS t FROM cal
  UNION ALL SELECT 'month', CAST(month_start_date AS STRING), MAX(date_key) FROM cal GROUP BY month_start_date
  UNION ALL SELECT 'year', CAST(calendar_year AS STRING), MAX(date_key) FROM cal GROUP BY calendar_year
  UNION ALL SELECT 'total', CAST(NULL AS STRING), MAX(date_key) FROM cal
),
grid AS (
  SELECT a.period, a.period_member, a.t, m.dim, m.member
  FROM anchors a JOIN members m ON m.dim = 'all'
  UNION ALL
  SELECT a.period, a.period_member, a.t, m.dim, m.member
  FROM anchors a JOIN members m ON m.dim <> 'all'
  WHERE a.period = 'month'
),
pace AS (
  SELECT g.period, g.period_member, g.dim, g.member, c.day_of_month, c.day_of_year,
         SUM(CASE WHEN d.pickup_date BETWEEN c.month_start_date AND g.t THEN d.trips END) AS mtd_trips,
         SUM(d.trips) AS ytd_trips
  FROM grid g
  JOIN cal c ON c.date_key = g.t
  LEFT JOIN daily d
    ON d.dim = g.dim AND d.member IS NOT DISTINCT FROM g.member
   AND d.pickup_date BETWEEN make_date(year(g.t), 1, 1) AND g.t
  GROUP BY g.period, g.period_member, g.dim, g.member, c.day_of_month, c.day_of_year
),
labeled AS (
  SELECT CASE WHEN dim = 'all' THEN period ELSE period || '_' || dim END AS grain,
         period_member AS member_1, member AS member_2, mtd_trips, ytd_trips, day_of_month, day_of_year
  FROM pace
)
SELECT grain, measure, member_1, member_2, member_3, value
FROM (
  SELECT grain, 'N-C2' AS measure, member_1, member_2, CAST(NULL AS STRING) AS member_3,
         (CAST(COALESCE(mtd_trips, 0) AS DOUBLE) / day_of_month)
           / NULLIF(CAST(ytd_trips AS DOUBLE) / day_of_year, 0) AS value
  FROM labeled
  UNION ALL
  SELECT grain, 'N-C2:mtd_trips', member_1, member_2, CAST(NULL AS STRING), CAST(mtd_trips AS DOUBLE) FROM labeled
  UNION ALL
  SELECT grain, 'N-C2:ytd_trips', member_1, member_2, CAST(NULL AS STRING), CAST(ytd_trips AS DOUBLE) FROM labeled
) r
ORDER BY grain, measure, member_1 NULLS FIRST, member_2 NULLS FIRST, member_3 NULLS FIRST
