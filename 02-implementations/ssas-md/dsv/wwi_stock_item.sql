-- DSV named query wwi_stock_item: database dimension Stock Item.
-- As-was attributes come from the surrogate row; current_color is the as-is color of the durable item
-- (the version with is_current = 1, SPEC § 5.3 rule 4); balance_basis is the snapshot derivation of the item
-- (SPEC § 5.3 rule 6).
SELECT
  s.stock_item_key,
  s.wwi_stock_item_id,
  CAST(s.wwi_stock_item_id AS VARCHAR(10)) AS wwi_stock_item_id_name,
  s.stock_item,
  s.color,
  c.color AS current_color,
  s.brand,
  s.size,
  s.selling_package,
  CASE WHEN s.is_chiller_stock = 1 THEN 'true' ELSE 'false' END AS is_chiller_stock,
  b.balance_basis
FROM wwi.dim_stock_item s
LEFT JOIN wwi.dim_stock_item c
  ON c.wwi_stock_item_id = s.wwi_stock_item_id AND c.is_current = 1
LEFT JOIN (
  SELECT h.wwi_stock_item_id, MAX(h.balance_basis) AS balance_basis
  FROM wwi.fact_stock_holding_daily h
  GROUP BY h.wwi_stock_item_id
) b ON b.wwi_stock_item_id = s.wwi_stock_item_id
