-- Q-W-C1-D2 FY2015 stock group share within each Sales Territory (denominator deduplicated per territory, range: all over stock_group).
SELECT sales_territory, stock_group AS stock_group_name, MEASURE(revenue) AS revenue,
       MEASURE(stock_group_revenue_share) AS share_of_territory
FROM slc.semantic.wwi_sales_by_stock_group
WHERE fiscal_year = 2015
GROUP BY sales_territory, stock_group
ORDER BY sales_territory, stock_group
