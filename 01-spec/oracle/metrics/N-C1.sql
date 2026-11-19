-- N-C1 Revenue YTD and YoY % vs STLY, anchored on the Pickup Date role. t = last calendar day of the period, capped at 2024-12-31.
-- YTD(t) = sum(total_amount), pickup_date in [Jan 1 of year(t), t]; STLY_YTD(t) = same for [Jan 1 of year(t) - 1, t - 1 year] (29 Feb -> 28 Feb);
-- YOY% = (YTD - STLY) / STLY; NULL for 2023 anchors (no prior-year data). Member grains: month x pickup borough, payment type, vendor, pickup hour.
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
ytd AS (
  SELECT g.period, g.period_member, g.dim, g.member,
         SUM(CASE WHEN d.pickup_date BETWEEN make_date(year(g.t), 1, 1) AND g.t THEN d.revenue END) AS ytd_revenue,
         SUM(CASE WHEN d.pickup_date BETWEEN make_date(year(g.t) - 1, 1, 1) AND CAST(g.t - INTERVAL '1' YEAR AS DATE)
                  THEN d.revenue END) AS stly_revenue
  FROM grid g
  LEFT JOIN daily d
    ON d.dim = g.dim AND d.member IS NOT DISTINCT FROM g.member
   AND d.pickup_date BETWEEN make_date(year(g.t) - 1, 1, 1) AND g.t
  GROUP BY g.period, g.period_member, g.dim, g.member
),
labeled AS (
  SELECT CASE WHEN dim = 'all' THEN period ELSE period || '_' || dim END AS grain,
         period_member AS member_1, member AS member_2, ytd_revenue, stly_revenue
  FROM ytd
)
SELECT grain, measure, member_1, member_2, member_3, value
FROM (
  SELECT grain, 'N-C1:ytd_revenue' AS measure, member_1, member_2, CAST(NULL AS STRING) AS member_3,
         CAST(ytd_revenue AS DOUBLE) AS value FROM labeled
  UNION ALL
  SELECT grain, 'N-C1:stly_ytd_revenue', member_1, member_2, CAST(NULL AS STRING), CAST(stly_revenue AS DOUBLE) FROM labeled
  UNION ALL
  SELECT grain, 'N-C1:yoy_pct', member_1, member_2, CAST(NULL AS STRING),
         (CAST(ytd_revenue AS DOUBLE) - CAST(stly_revenue AS DOUBLE)) / NULLIF(CAST(stly_revenue AS DOUBLE), 0) FROM labeled
) r
ORDER BY grain, measure, member_1 NULLS FIRST, member_2 NULLS FIRST, member_3 NULLS FIRST
