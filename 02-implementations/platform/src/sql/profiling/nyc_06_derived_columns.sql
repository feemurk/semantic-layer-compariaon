-- P-NYC-06 derived trip columns are consistent with their sources (pickup_date, dropoff_date, pickup_hour, od_pair_id)
SELECT trip_id
FROM nyctaxi.fact_trip
WHERE pickup_date <> CAST(pickup_ts AS DATE)
   OR dropoff_date <> CAST(dropoff_ts AS DATE)
   OR pickup_hour <> HOUR(pickup_ts)
   OR od_pair_id <> pu_location_id * 1000 + do_location_id
   OR trip_id DIV 100 <> TIMESTAMPDIFF(SECOND, TIMESTAMP_NTZ'1970-01-01 00:00:00', pickup_ts)
