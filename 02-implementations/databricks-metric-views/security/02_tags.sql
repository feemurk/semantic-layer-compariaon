-- SPEC § 10, governed profile: tags that bind the ABAC policies to tables and key columns.
-- slc_rls_scope and slc_rls_key are governed tags created by an account admin beforehand
-- (allowed values: slc_rls_scope = sales_territory | inventory | pickup_borough; slc_rls_key = city_key | pu_location_id).
-- Tags attach to the pipeline-managed gold tables without changing their pipeline definitions.
SET TAG ON TABLE slc.wwi.fact_sale slc_rls_scope = sales_territory;
SET TAG ON COLUMN slc.wwi.fact_sale.city_key slc_rls_key = city_key;
SET TAG ON TABLE slc.wwi.fact_order slc_rls_scope = sales_territory;
SET TAG ON COLUMN slc.wwi.fact_order.city_key slc_rls_key = city_key;
SET TAG ON TABLE slc.wwi.fact_stock_holding_daily slc_rls_scope = inventory;
SET TAG ON TABLE slc.wwi.fact_stock_movement slc_rls_scope = inventory;
SET TAG ON TABLE slc.wwi.stock_holding_current slc_rls_scope = inventory;
SET TAG ON TABLE slc.nyctaxi.fact_trip slc_rls_scope = pickup_borough;
SET TAG ON COLUMN slc.nyctaxi.fact_trip.pu_location_id slc_rls_key = pu_location_id;
