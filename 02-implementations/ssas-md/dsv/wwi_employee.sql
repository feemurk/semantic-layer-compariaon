-- DSV named query wwi_employee: database dimension Employee, role-played as Salesperson and Picker.
-- The Employee attribute is keyed by name, so SCD2 versions of one employee aggregate to one member.
SELECT
  e.employee_key,
  e.employee
FROM wwi.dim_employee e
