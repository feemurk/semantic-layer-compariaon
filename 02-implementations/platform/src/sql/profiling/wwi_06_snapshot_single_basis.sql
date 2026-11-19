-- P-WWI-06 each stock item uses exactly one balance basis for the whole window (SPEC § 5.3 rule 6)
SELECT wwi_stock_item_id, COUNT(DISTINCT balance_basis) AS bases
FROM wwi.fact_stock_holding_daily
GROUP BY wwi_stock_item_id
HAVING COUNT(DISTINCT balance_basis) <> 1
    OR MAX(balance_basis) NOT IN ('holding_backcast', 'flow_min_opening')
