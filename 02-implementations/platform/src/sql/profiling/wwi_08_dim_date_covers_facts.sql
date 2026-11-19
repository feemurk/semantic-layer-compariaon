-- P-WWI-08 wwi.dim_date is gap-free over 2013-2016 and covers every fact date (SPEC § 5.4)
SELECT 'gap or range error' AS violation, CAST(NULL AS DATE) AS missing_date
FROM (SELECT COUNT(*) AS n, MIN(date_key) AS mn, MAX(date_key) AS mx FROM wwi.dim_date) d
WHERE n <> DATEDIFF(mx, mn) + 1 OR mn <> DATE'2013-01-01' OR mx <> DATE'2016-12-31'
UNION ALL
SELECT 'fact date outside dim_date', f.d
FROM (
  SELECT invoice_date AS d FROM wwi.fact_sale
  UNION SELECT delivery_date FROM wwi.fact_sale WHERE delivery_date IS NOT NULL
  UNION SELECT order_date FROM wwi.fact_order
  UNION SELECT movement_date FROM wwi.fact_stock_movement
  UNION SELECT snapshot_date FROM wwi.fact_stock_holding_daily
) f
LEFT ANTI JOIN wwi.dim_date d ON d.date_key = f.d
