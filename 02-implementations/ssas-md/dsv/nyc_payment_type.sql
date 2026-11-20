-- DSV named query nyc_payment_type: database dimension Payment Type (TLC codes 0-6).
SELECT
  p.payment_type,
  CAST(p.payment_type AS VARCHAR(2)) AS payment_type_code_name,
  p.payment_type_name
FROM nyctaxi.dim_payment_type p
