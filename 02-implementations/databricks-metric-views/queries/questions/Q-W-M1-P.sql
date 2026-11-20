-- Q-W-M1-P Gross margin % by customer category by fiscal quarter, FY2015 (composed measure gross_margin_pct).
SELECT customer_category, fiscal_quarter, MEASURE(revenue) AS revenue, MEASURE(gross_profit) AS profit,
       MEASURE(gross_margin_pct) AS gross_margin_pct
FROM slc.semantic.wwi_sales
WHERE fiscal_year = 2015
GROUP BY customer_category, fiscal_quarter
ORDER BY customer_category, fiscal_quarter
