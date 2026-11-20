-- Q-W-C2-D4 Days of supply by Sales Territory at 2015-12-31: slc.semantic.wwi_stock exposes no territory (non-conformed dimension),
-- so the answer is NULL for every territory; territories are listed from slc.semantic.wwi_sales.
WITH territories AS (SELECT sales_territory, MEASURE(units_sold) AS u FROM slc.semantic.wwi_sales GROUP BY sales_territory)
SELECT sales_territory, CAST(NULL AS DOUBLE) AS days_of_supply,
       'non-conformed dimension: stock holdings carry no city' AS reason
FROM territories
ORDER BY sales_territory
