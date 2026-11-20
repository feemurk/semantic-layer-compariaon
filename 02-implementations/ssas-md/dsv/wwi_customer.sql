-- DSV named query wwi_customer: database dimension Customer, role-played as Customer and Bill To Customer.
-- The Customer attribute is keyed by name, so SCD2 versions of one customer aggregate to one member.
SELECT
  c.customer_key,
  c.customer,
  c.category,
  c.buying_group
FROM wwi.dim_customer c
