-- Q-N-M1-D3 Distinct OD pairs served by each vendor, 2023 vs 2024.
SELECT f.vendor_id,
       COUNT(DISTINCT CASE WHEN d.calendar_year = 2023 THEN f.od_pair_id END) AS distinct_od_pairs_2023,
       COUNT(DISTINCT CASE WHEN d.calendar_year = 2024 THEN f.od_pair_id END) AS distinct_od_pairs_2024
FROM nyctaxi.fact_trip f
JOIN nyctaxi.dim_date d ON d.date_key = f.pickup_date
GROUP BY f.vendor_id
ORDER BY f.vendor_id
