# Verified answers (Copilot in Power BI)

Verified answers bind a report visual to trigger phrases. Microsoft documents that CI/CD is not supported for them:
Git integration, REST APIs and deployment pipelines do not carry them
(https://learn.microsoft.com/en-us/power-bi/create-reports/copilot-prepare-data-ai-verified-answers, checked 2026-11-20).
They are therefore configured in the service after each first deployment to a workspace, and E5 counts this as a
manual step (boundary B-NEW-2 in POWERBI_TABULAR_GUIDE.md).

The study registers one verified answer per predefined executive question; the visual reproduces the query in
`queries/questions/<id>.dax`.

| Question | Model | Trigger phrases | Visual (fields) |
|---|---|---|---|
| Q-W-S1-P | SLC WWI | revenue by territory by fiscal month FY2015; FY2015 territory revenue | Matrix: 'City'[Sales Territory] x 'Date'[Fiscal Month], [Revenue (Excl. Tax)], filter Fiscal Year = 2015 |
| Q-W-S2-P | SLC WWI | ordered quantity and revenue by month 2015 | Line chart: 'Date'[Month Start], [Ordered Quantity], [Revenue (Excl. Tax)], filter Calendar Year = 2015 |
| Q-W-M1-P | SLC WWI | gross margin by customer category by fiscal quarter FY2015 | Matrix: 'Customer'[Customer Category] x 'Date'[Fiscal Quarter], [Gross Margin %], filter Fiscal Year = 2015 |
| Q-W-M2-P | SLC WWI | closing stock at each fiscal month end FY2015 | Column chart: 'Date'[Fiscal Month], [Closing Stock On Hand], filter Fiscal Year = 2015 |
| Q-W-C1-P | SLC WWI | revenue share by stock group FY2015 | Table: 'Stock Group'[Stock Group], [Revenue (Excl. Tax)], [Stock Group Revenue Share], totals on, filter Fiscal Year = 2015 |
| Q-W-C2-P | SLC WWI | days of supply by month end 2015 | Line chart: 'Date'[Month Start], [Days of Supply], filter Calendar Year = 2015 |
| Q-N-S1-P | SLC NYC | trip revenue by borough by month 2024 | Matrix: 'Pickup Zone'[Pickup Borough] x 'Pickup Date'[Pickup Month Start], [Gross Trip Revenue], filter Pickup Calendar Year = 2024 |
| Q-N-S2-P | SLC NYC | card tips by vendor by month 2024 | Matrix: 'Trips'[Vendor ID] x 'Pickup Date'[Pickup Month Start], [Card Tips], filter Pickup Calendar Year = 2024 |
| Q-N-M1-P | SLC NYC | distinct origin destination pairs by month 2024 | Column chart: 'Pickup Date'[Pickup Month Start], [Distinct OD Pairs], filter Pickup Calendar Year = 2024 |
| Q-N-M2-P | SLC NYC | fare per mile pickup borough by dropoff borough 2024 | Matrix: 'Pickup Zone'[Pickup Borough] x 'Dropoff Zone'[Dropoff Borough], [Fare per Mile], filter Pickup Calendar Year = 2024 |
| Q-N-C1-P | SLC NYC | YTD revenue and YoY at each month end 2024 | Table: 'Pickup Date'[Pickup Month Start], [Revenue YTD], [Revenue STLY YTD], [Revenue YoY % vs STLY], filter Pickup Calendar Year = 2024 |
| Q-N-C2-P | SLC NYC | pace index at each month end 2024 | Line chart: 'Pickup Date'[Pickup Month Start], [MTD-to-YTD Daily Pace Index], filter Pickup Calendar Year = 2024 |
