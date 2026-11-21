# AI instructions: SLC WWI

Applied through Prep data for AI > Add AI instructions on each SLC_WWI_* model. The service stores them in the model's
linguistic schema (LSDL), which then travels with Git and deployment; refresh the model after deployment so Copilot reads
the updated LSDL.

## Metrics
- "Revenue", "sales" and "turnover" mean the measure Revenue (Excl. Tax). Use Revenue Including Tax only when the user says "including tax".
- Margin questions use Gross Margin %, a ratio of sums. Never average Gross Margin % across rows.
- Stock on hand uses Closing Stock On Hand: the units on the last snapshot date of the selected period. Never sum it across dates.
- Days of supply uses Days of Supply. It is defined only by date, stock item and stock group. For customer, city, territory, salesperson or picker it is blank by design; say so instead of computing another figure.
- Backorders use Backordered Order Lines.

## Dates and fiscal year
- The fiscal year starts on 1 November and is named after the calendar year in which it ends: FY2015 = 2014-11-01 to 2015-10-31. Use 'Date'[Fiscal Year] for "FY" questions and 'Date'[Calendar Year] otherwise.
- One shared Date table filters sales by invoice date, orders by order date and stock by snapshot date. "Delivered in" questions use the Delivery Date table.

## Stock groups
- A stock item can belong to several stock groups. Totals across groups count each sale once. The sum of group values is larger than the total; never present that sum as total revenue.
- Use Stock Group Revenue Share for "share of revenue by stock group".

## Attribution
- Customer, City and Stock Item attributes are as recorded at the time of the transaction. For current values of a stock item ("current color", "today's package"), use the Stock Item (Current) table.
