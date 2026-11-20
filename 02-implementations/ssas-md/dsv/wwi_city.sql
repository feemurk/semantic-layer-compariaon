-- DSV named query wwi_city: database dimension City (as-was geography of sales and orders, SPEC § 5.3 rule 4).
-- City members are keyed by (state_province, city): city names repeat across states.
SELECT
  c.city_key,
  c.city,
  c.state_province,
  c.country,
  c.continent,
  c.sales_territory
FROM wwi.dim_city c
