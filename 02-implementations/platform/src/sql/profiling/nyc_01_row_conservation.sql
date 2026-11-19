-- P-NYC-01 every bronze row lands in exactly one of fact_trip or fact_trip_quarantine (SPEC § 5.3 rule 1)
SELECT bronze_rows, fact_rows, quarantine_rows
FROM (
  SELECT (SELECT COUNT(*) FROM raw_nyctaxi.trips_bronze) AS bronze_rows,
         (SELECT COUNT(*) FROM nyctaxi.fact_trip) AS fact_rows,
         (SELECT COUNT(*) FROM nyctaxi.fact_trip_quarantine) AS quarantine_rows
) c
WHERE bronze_rows <> fact_rows + quarantine_rows OR fact_rows = 0
