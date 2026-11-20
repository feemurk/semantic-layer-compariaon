-- DSV named query wwi_inventory_access: one-member security dimension related only to Stock Holdings.
-- The Territory Analyst role allows none of its members with visual totals, so inventory measures are empty
-- for that role while sales and orders are unaffected (SPEC § 10).
SELECT
  1 AS access_key,
  'Granted' AS access_name
