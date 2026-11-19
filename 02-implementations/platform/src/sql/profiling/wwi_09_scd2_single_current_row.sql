-- P-WWI-09 SCD Type 2 current flag matches the open-ended validity row, one current row per durable key (SPEC § 5.3 rule 4)
SELECT 'dim_stock_item' AS dim, wwi_stock_item_id AS durable_key, COUNT_IF(is_current) AS current_rows
FROM wwi.dim_stock_item GROUP BY wwi_stock_item_id HAVING COUNT_IF(is_current) <> 1
UNION ALL
SELECT 'dim_customer', wwi_customer_id, COUNT_IF(is_current) FROM wwi.dim_customer GROUP BY wwi_customer_id HAVING COUNT_IF(is_current) <> 1
UNION ALL
SELECT 'dim_city', wwi_city_id, COUNT_IF(is_current) FROM wwi.dim_city GROUP BY wwi_city_id HAVING COUNT_IF(is_current) <> 1
UNION ALL
SELECT 'dim_employee', wwi_employee_id, COUNT_IF(is_current) FROM wwi.dim_employee GROUP BY wwi_employee_id HAVING COUNT_IF(is_current) <> 1
