-- P-NYC-04 no pickup second exceeds the 100 trip_id ordinal slots (trip_id = epoch seconds * 100 + ordinal)
SELECT tpep_pickup_datetime, COUNT(*) AS trips_in_second
FROM raw_nyctaxi.trips_bronze
GROUP BY tpep_pickup_datetime
HAVING COUNT(*) > 100
