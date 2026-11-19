-- P-WWI-01 wwi.dim_date calendar and fiscal columns equal [Dimension].[Date] for every date (SPEC § 5.4)
SELECT COALESCE(d.date_key, CAST(s.`Date` AS DATE)) AS date_key,
       d.fiscal_year, s.`Fiscal Year` AS source_fiscal_year,
       d.fiscal_month, s.`Fiscal Month Number` AS source_fiscal_month
FROM raw_wwi.dw_dimension_date s
FULL OUTER JOIN wwi.dim_date d ON d.date_key = CAST(s.`Date` AS DATE)
WHERE d.date_key IS NULL
   OR s.`Date` IS NULL
   OR d.fiscal_year <> s.`Fiscal Year`
   OR d.fiscal_month <> s.`Fiscal Month Number`
   OR d.calendar_year <> s.`Calendar Year`
   OR d.calendar_month <> s.`Calendar Month Number`
