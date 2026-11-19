-- Q-W-C2-D4 Days of supply by Sales Territory at 2015-12-31: Sales Territory is not a conformed dimension of the stock
-- snapshot (SPEC § 6.5, W-C2 CITY = N), so every territory's value is NULL. Lists every territory with sales.
SELECT DISTINCT ci.sales_territory, CAST(NULL AS DOUBLE) AS days_of_supply,
       'non-conformed dimension: stock holdings carry no city' AS reason
FROM wwi.fact_sale f
JOIN wwi.dim_city ci ON ci.city_key = f.city_key
ORDER BY ci.sales_territory
