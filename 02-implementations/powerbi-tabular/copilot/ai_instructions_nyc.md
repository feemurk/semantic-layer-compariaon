# AI instructions: SLC NYC

Applied through Prep data for AI > Add AI instructions on each SLC_NYC_* model; stored in the linguistic schema
(LSDL) and carried by Git and deployment; refresh the model after deployment.

## Metrics
- "Revenue" means Gross Trip Revenue (total amount charged). "Fares" means Fare Amount.
- "Tips" means Card Tips unless the user explicitly asks for all payment types (Tip Amount (All Payment Types)). TLC records tips only for card payments.
- Fare per Mile is a ratio of sums. Never average it across rows.
- Distinct OD Pairs is an exact distinct count and is not additive: never sum it across months, payment types, vendors or hours.

## Dates and roles
- Trips are dated by pickup unless the user says dropoff. Pickup Date and Dropoff Date are separate tables, as are Pickup Zone and Dropoff Zone.
- Year-to-date and pace questions use Revenue YTD, Revenue STLY YTD, Revenue YoY % vs STLY, Trips MTD, Trips YTD and MTD-to-YTD Daily Pace Index. Anchor them by filtering 'Pickup Date'[Pickup Date] to the requested day, or by grouping by month. The anchor is the last calendar day of the period, capped at 2024-12-31.
- These time-intelligence measures are blank when grouped by Dropoff Date, by design.

## Geography
- "Airports" refers to 'Pickup Zone'[Pickup Service Zone] = "Airports". JFK and LaGuardia are zones ('Pickup Zone'[Pickup Zone] = "JFK Airport" or "LaGuardia Airport").
