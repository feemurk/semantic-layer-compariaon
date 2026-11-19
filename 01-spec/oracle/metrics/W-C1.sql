-- W-C1 Stock Group Revenue Share: REV(g) = sum(total_excluding_tax) of sale lines whose item belongs to g; SHARE(g) = REV(g) / REV(context without the stock group filter).
-- Totals across groups are deduplicated: the *_all_groups grains equal REV(context) / REV(context) = 1, never the sum of group shares.
WITH base AS (
  SELECT f.total_excluding_tax AS revenue, d.calendar_year, d.fiscal_year,
         ci.sales_territory, c.category AS customer_category, si.wwi_stock_item_id
  FROM wwi.fact_sale f
  JOIN wwi.dim_date d ON d.date_key = f.invoice_date
  JOIN wwi.dim_city ci ON ci.city_key = f.city_key
  JOIN wwi.dim_customer c ON c.customer_key = f.customer_key
  JOIN wwi.dim_stock_item si ON si.stock_item_key = f.stock_item_key
),
grp AS (
  SELECT base.*, g.stock_group_name
  FROM base
  JOIN wwi.bridge_stock_item_group b ON b.wwi_stock_item_id = base.wwi_stock_item_id
  JOIN wwi.dim_stock_group g ON g.stock_group_id = b.stock_group_id
),
ctx_total AS (SELECT SUM(revenue) AS rev FROM base),
ctx_year AS (SELECT calendar_year, SUM(revenue) AS rev FROM base GROUP BY calendar_year),
ctx_fiscal AS (SELECT fiscal_year, SUM(revenue) AS rev FROM base GROUP BY fiscal_year),
ctx_territory AS (SELECT calendar_year, sales_territory, SUM(revenue) AS rev FROM base GROUP BY calendar_year, sales_territory),
ctx_category AS (SELECT calendar_year, customer_category, SUM(revenue) AS rev FROM base GROUP BY calendar_year, customer_category),
g_total AS (SELECT stock_group_name, SUM(revenue) AS rev FROM grp GROUP BY stock_group_name),
g_year AS (SELECT calendar_year, stock_group_name, SUM(revenue) AS rev FROM grp GROUP BY calendar_year, stock_group_name),
g_fiscal AS (SELECT fiscal_year, stock_group_name, SUM(revenue) AS rev FROM grp GROUP BY fiscal_year, stock_group_name),
g_territory AS (SELECT calendar_year, sales_territory, stock_group_name, SUM(revenue) AS rev FROM grp GROUP BY calendar_year, sales_territory, stock_group_name),
g_category AS (SELECT calendar_year, customer_category, stock_group_name, SUM(revenue) AS rev FROM grp GROUP BY calendar_year, customer_category, stock_group_name)
SELECT grain, measure, member_1, member_2, member_3, value
FROM (
  SELECT 'total_stock_group' AS grain, 'W-C1' AS measure, g.stock_group_name AS member_1, CAST(NULL AS STRING) AS member_2,
         CAST(NULL AS STRING) AS member_3, CAST(g.rev AS DOUBLE) / NULLIF(CAST(c.rev AS DOUBLE), 0) AS value
  FROM g_total g CROSS JOIN ctx_total c
  UNION ALL
  SELECT 'total_all_groups', 'W-C1', CAST(NULL AS STRING), CAST(NULL AS STRING), CAST(NULL AS STRING),
         CAST(c.rev AS DOUBLE) / NULLIF(CAST(c.rev AS DOUBLE), 0)
  FROM ctx_total c
  UNION ALL
  SELECT 'year_stock_group', 'W-C1', CAST(g.calendar_year AS STRING), g.stock_group_name, CAST(NULL AS STRING),
         CAST(g.rev AS DOUBLE) / NULLIF(CAST(c.rev AS DOUBLE), 0)
  FROM g_year g JOIN ctx_year c ON c.calendar_year = g.calendar_year
  UNION ALL
  SELECT 'year_all_groups', 'W-C1', CAST(c.calendar_year AS STRING), CAST(NULL AS STRING), CAST(NULL AS STRING),
         CAST(c.rev AS DOUBLE) / NULLIF(CAST(c.rev AS DOUBLE), 0)
  FROM ctx_year c
  UNION ALL
  SELECT 'fiscal_year_stock_group', 'W-C1', CAST(g.fiscal_year AS STRING), g.stock_group_name, CAST(NULL AS STRING),
         CAST(g.rev AS DOUBLE) / NULLIF(CAST(c.rev AS DOUBLE), 0)
  FROM g_fiscal g JOIN ctx_fiscal c ON c.fiscal_year = g.fiscal_year
  UNION ALL
  SELECT 'year_sales_territory_stock_group', 'W-C1', CAST(g.calendar_year AS STRING), g.sales_territory, g.stock_group_name,
         CAST(g.rev AS DOUBLE) / NULLIF(CAST(c.rev AS DOUBLE), 0)
  FROM g_territory g JOIN ctx_territory c ON c.calendar_year = g.calendar_year AND c.sales_territory = g.sales_territory
  UNION ALL
  SELECT 'year_customer_category_stock_group', 'W-C1', CAST(g.calendar_year AS STRING), g.customer_category, g.stock_group_name,
         CAST(g.rev AS DOUBLE) / NULLIF(CAST(c.rev AS DOUBLE), 0)
  FROM g_category g JOIN ctx_category c ON c.calendar_year = g.calendar_year AND c.customer_category = g.customer_category
) r
ORDER BY grain, measure, member_1 NULLS FIRST, member_2 NULLS FIRST, member_3 NULLS FIRST
