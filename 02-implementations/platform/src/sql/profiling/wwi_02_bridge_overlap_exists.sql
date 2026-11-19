-- P-WWI-02 at least one stock item belongs to two or more stock groups (W-C1 fan-out precondition, SPEC § 6.3)
SELECT 'no stock item belongs to two or more stock groups' AS violation
FROM (SELECT 1 AS one) t
WHERE NOT EXISTS (
  SELECT wwi_stock_item_id
  FROM wwi.bridge_stock_item_group
  GROUP BY wwi_stock_item_id
  HAVING COUNT(*) >= 2
)
