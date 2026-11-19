-- P-WWI-07 gold fact and dimension row counts equal their bronze sources (no rows dropped or duplicated, SPEC § 5.3 rule 3)
SELECT table_name, gold_rows, bronze_rows
FROM (
  SELECT 'fact_sale' AS table_name, (SELECT COUNT(*) FROM wwi.fact_sale) AS gold_rows, (SELECT COUNT(*) FROM raw_wwi.dw_fact_sale) AS bronze_rows
  UNION ALL SELECT 'fact_order', (SELECT COUNT(*) FROM wwi.fact_order), (SELECT COUNT(*) FROM raw_wwi.dw_fact_order)
  UNION ALL SELECT 'fact_stock_movement', (SELECT COUNT(*) FROM wwi.fact_stock_movement), (SELECT COUNT(*) FROM raw_wwi.dw_fact_movement)
  UNION ALL SELECT 'stock_holding_current', (SELECT COUNT(*) FROM wwi.stock_holding_current), (SELECT COUNT(*) FROM raw_wwi.dw_fact_stock_holding)
  UNION ALL SELECT 'dim_stock_item', (SELECT COUNT(*) FROM wwi.dim_stock_item), (SELECT COUNT(*) FROM raw_wwi.dw_dimension_stock_item)
  UNION ALL SELECT 'dim_customer', (SELECT COUNT(*) FROM wwi.dim_customer), (SELECT COUNT(*) FROM raw_wwi.dw_dimension_customer)
  UNION ALL SELECT 'dim_city', (SELECT COUNT(*) FROM wwi.dim_city), (SELECT COUNT(*) FROM raw_wwi.dw_dimension_city)
  UNION ALL SELECT 'dim_employee', (SELECT COUNT(*) FROM wwi.dim_employee), (SELECT COUNT(*) FROM raw_wwi.dw_dimension_employee)
  UNION ALL SELECT 'dim_stock_group', (SELECT COUNT(*) FROM wwi.dim_stock_group), (SELECT COUNT(*) FROM raw_wwi.oltp_warehouse_stockgroups)
  UNION ALL SELECT 'bridge_stock_item_group', (SELECT COUNT(*) FROM wwi.bridge_stock_item_group), (SELECT COUNT(*) FROM raw_wwi.oltp_warehouse_stockitemstockgroups)
) c
WHERE gold_rows <> bronze_rows OR gold_rows = 0
