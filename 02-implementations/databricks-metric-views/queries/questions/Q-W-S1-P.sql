-- Q-W-S1-P Revenue (excl. tax) by Sales Territory by fiscal month for FY2015, through slc.semantic.wwi_sales.
SELECT sales_territory, fiscal_month, month_start_date, MEASURE(revenue) AS revenue
FROM slc.semantic.wwi_sales
WHERE fiscal_year = 2015
GROUP BY sales_territory, fiscal_month, month_start_date
ORDER BY sales_territory, fiscal_month
