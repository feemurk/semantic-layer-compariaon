-- Q-N-S2-D4 Card tips by payment type for 2024: a value for type 1, NULL for every other type with 2024 trips.
-- A metric view exposes dimension members only through facts, so payment codes without 2024 trips are absent
-- (the oracle lists all seven codes; the difference is reported by reconciliation, not padded here).
SELECT payment_type, payment_type_name, MEASURE(card_tips) AS card_tips
FROM slc.semantic.nyc_trips WHERE YEAR(pickup_year) = 2024
GROUP BY payment_type, payment_type_name
ORDER BY payment_type
