"""Single definition of the three Tableau published data sources of stack S3 (SPEC § 3.1).

build_tableau.py renders these definitions to .tds XML, lint_tableau.py checks them, and the jobs read the published
names. Physical tables are custom SQL relations with prefixed column aliases, so every field has a deterministic,
unique local name across logical tables (role-played dimensions, two facts carrying the same column names).

Agent metadata (field descriptions) comes from 01-spec/glossary.yaml. Tableau has no field-level synonym property in a
data source; synonyms are appended to the description, which is what Tableau Agent indexes (guide § 2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
GLOSSARY = yaml.safe_load((REPO / "01-spec" / "glossary.yaml").read_text())
METRICS = {m["id"]: m for m in GLOSSARY["metrics"]}
DIMS = {d["name"]: d for ds in GLOSSARY["dimensions"].values() for d in ds}

TERRITORY_GROUP = "slc_territory_southeast"
PICKUP_GROUP = "slc_pickup_manhattan"
CONNECTION = "databricks.slc"

# Tableau number formats by glossary format key.
FORMATS = {
    "currency": 'c"$"#,##0.00;-"$"#,##0.00',
    "units": "n#,##0",
    "count": "n#,##0",
    "ratio_pct": "p0.00%",
    "decimal_2": "n#,##0.00",
    "days": "n#,##0.0",
    "index": "n#,##0.000",
}


@dataclass
class Col:
    """A physical column of a logical table (alias in the custom SQL)."""
    name: str
    caption: str
    datatype: str  # string | integer | real | date | datetime | boolean
    role: str = "dimension"
    hidden: bool = False
    desc: str | None = None

    @property
    def type(self) -> str:
        if self.role == "measure":
            return "quantitative"
        return "nominal" if self.datatype in ("string", "boolean") else "ordinal"


@dataclass
class Calc:
    name: str
    caption: str
    formula: str
    datatype: str
    role: str = "measure"
    hidden: bool = False
    desc: str | None = None
    fmt: str | None = None
    metric_id: str | None = None

    @property
    def type(self) -> str:
        if self.role == "measure":
            return "quantitative"
        return "nominal" if self.datatype in ("string", "boolean") else "ordinal"


@dataclass
class Param:
    name: str
    caption: str
    datatype: str
    value: str  # Tableau literal, e.g. #2024-12-31#
    desc: str


@dataclass
class Table:
    id: str
    caption: str
    sql: str
    cols: list[Col]
    desc: str


@dataclass
class Rel:
    first: str   # table id (fact side; base tables are the roots of the relationship trees)
    second: str  # table id (dimension side)
    pairs: list[tuple[str, str]]  # (first column, second column), ANDed equalities


@dataclass
class RlsFilter:
    calc: str
    logical_table_scoped: bool
    rationale: str


@dataclass
class DataSource:
    key: str
    name: str  # published data source name (live variant)
    caption: str
    desc: str
    tables: list[Table]
    rels: list[Rel]
    calcs: list[Calc]
    params: list[Param] = field(default_factory=list)
    rls: list[RlsFilter] = field(default_factory=list)
    incremental_key: str | None = None  # extract variant: column for "identify new rows"

    @property
    def file(self) -> str:
        return f"{self.key}.tds"

    @property
    def extract_name(self) -> str:
        return f"{self.name} (Extract)"

    def columns(self) -> list[Col]:
        return [c for t in self.tables for c in t.cols]

    def fields(self) -> dict[str, object]:
        """caption -> Col | Calc | Param for every queryable field."""
        out: dict[str, object] = {}
        for item in [*self.columns(), *self.calcs, *self.params]:
            out[item.caption] = item
        return out

    def names(self) -> dict[str, object]:
        """local name -> Col | Calc | Param."""
        return {i.name: i for i in [*self.columns(), *self.calcs, *self.params]}


def describe(text: str, synonyms: list[str] | None = None) -> str:
    syn = [s for s in (synonyms or []) if s]
    return f"{text} Also called: {', '.join(syn)}." if syn else text


def metric_desc(metric_id: str, extra: str | None = None) -> str:
    m = METRICS[metric_id]
    text = m["description"] if not extra else f"{m['description']} {extra}"
    return describe(text, m.get("synonyms"))


def dim_desc(dim: str, extra: str | None = None) -> str:
    d = DIMS[dim]
    text = d["description"] if not extra else f"{d['description']} {extra}"
    return describe(text, d.get("synonyms"))


def metric_calc(metric_id: str, name: str, formula: str, datatype: str = "real", extra: str | None = None) -> Calc:
    m = METRICS[metric_id]
    return Calc(name, m["display_name"], formula, datatype, desc=metric_desc(metric_id, extra),
                fmt=FORMATS[m["format"]], metric_id=metric_id)


def date_table(table_id: str, caption: str, prefix: str, schema: str, captions: dict[str, str], key_caption: str | None,
               desc: str) -> Table:
    """dim_date columns aliased with a prefix; captions maps column -> caption (unlisted columns are hidden)."""
    columns = [
        ("date_key", "date"), ("calendar_year", "integer"), ("calendar_quarter", "integer"),
        ("calendar_month", "integer"), ("month_name", "string"), ("month_start_date", "date"),
        ("day_of_month", "integer"), ("day_of_year", "integer"), ("day_of_week", "integer"), ("day_name", "string"),
        ("fiscal_year", "integer"), ("fiscal_quarter", "integer"), ("fiscal_month", "integer"),
    ]
    select = ", ".join(f"{c} AS {prefix}{c}" for c, _ in columns)
    cols = []
    for c, dt in columns:
        cap = key_caption if c == "date_key" and key_caption else captions.get(c)
        cols.append(Col(f"{prefix}{c}", cap or f"{caption} {c}", dt, hidden=cap is None))
    return Table(table_id, caption, f"SELECT {select} FROM slc.{schema}.dim_date", cols, desc)


# =========================================================================== WWI sales and orders (multi-fact)

WWI_DATE_CAPTIONS = {
    "calendar_year": "Calendar Year", "calendar_quarter": "Calendar Quarter", "calendar_month": "Calendar Month",
    "month_name": "Month Name", "month_start_date": "Month Start Date", "day_of_week": "Day of Week",
    "fiscal_year": "Fiscal Year", "fiscal_quarter": "Fiscal Quarter", "fiscal_month": "Fiscal Month",
}

STOCK_ITEM = Table(
    "stock_item", "Stock Item",
    "SELECT stock_item_key AS si_stock_item_key, wwi_stock_item_id AS si_wwi_stock_item_id, stock_item AS si_stock_item, "
    "brand AS si_brand, color AS si_color, size AS si_size, selling_package AS si_selling_package, "
    "is_chiller_stock AS si_is_chiller_stock FROM slc.wwi.dim_stock_item",
    [
        Col("si_stock_item_key", "Stock Item Key", "integer", hidden=True),
        Col("si_wwi_stock_item_id", "WWI Stock Item ID", "integer", desc="Durable stock item id, stable across SCD2 versions."),
        Col("si_stock_item", "Stock Item", "string", desc=dim_desc("stock_item")),
        Col("si_brand", "Brand", "string"),
        Col("si_color", "Color", "string", desc="Stock item color as recorded at the time of the fact (as-was, SCD2)."),
        Col("si_size", "Size", "string"),
        Col("si_selling_package", "Selling Package", "string"),
        Col("si_is_chiller_stock", "Is Chiller Stock", "boolean"),
    ],
    "Stock item version referenced by the fact's surrogate key (as-was attribution).",
)

CURRENT_STOCK_ITEM = Table(
    "current_stock_item", "Current Stock Item",
    "SELECT wwi_stock_item_id AS csi_wwi_stock_item_id, stock_item AS csi_stock_item, color AS csi_color "
    "FROM slc.wwi.dim_stock_item WHERE is_current",
    [
        Col("csi_wwi_stock_item_id", "Current Stock Item ID", "integer", hidden=True),
        Col("csi_stock_item", "Current Stock Item", "string", desc="Stock item name in its current version (as-is)."),
        Col("csi_color", "Current Color", "string", desc="Stock item color in its current version (as-is, SCD2)."),
    ],
    "Current version of each stock item, related through the durable id (as-is attribution).",
)

STOCK_GROUP = Table(
    "stock_group", "Stock Group Membership",
    "SELECT b.wwi_stock_item_id AS sg_wwi_stock_item_id, g.stock_group_id AS sg_stock_group_id, "
    "g.stock_group_name AS sg_stock_group_name FROM slc.wwi.bridge_stock_item_group b "
    "JOIN slc.wwi.dim_stock_group g ON g.stock_group_id = b.stock_group_id",
    [
        Col("sg_wwi_stock_item_id", "Stock Group Item ID", "integer", hidden=True),
        Col("sg_stock_group_id", "Stock Group ID", "integer", hidden=True),
        Col("sg_stock_group_name", "Stock Group", "string", desc=dim_desc("stock_group")),
    ],
    "Stock item to stock group membership (many-to-many bridge with group names).",
)

SALES = Table(
    "sales", "Sales",
    "SELECT sale_key AS sale_key, invoice_date AS sale_invoice_date, delivery_date AS sale_delivery_date, "
    "city_key AS sale_city_key, customer_key AS sale_customer_key, bill_to_customer_key AS sale_bill_to_customer_key, "
    "stock_item_key AS sale_stock_item_key, salesperson_key AS sale_salesperson_key, "
    "wwi_invoice_id AS sale_wwi_invoice_id, quantity AS sale_quantity, total_excluding_tax AS sale_total_excluding_tax, "
    "profit AS sale_profit, total_including_tax AS sale_total_including_tax FROM slc.wwi.fact_sale",
    [
        Col("sale_key", "Sale Key", "integer", hidden=True),
        Col("sale_invoice_date", "Invoice Date", "date", desc="Date of the invoice (the sales fact's primary date)."),
        Col("sale_delivery_date", "Sale Delivery Date Key", "date", hidden=True),
        Col("sale_city_key", "Sale City Key", "integer", hidden=True),
        Col("sale_customer_key", "Sale Customer Key", "integer", hidden=True),
        Col("sale_bill_to_customer_key", "Sale Bill-To Customer Key", "integer", hidden=True),
        Col("sale_stock_item_key", "Sale Stock Item Key", "integer", hidden=True),
        Col("sale_salesperson_key", "Sale Salesperson Key", "integer", hidden=True),
        Col("sale_wwi_invoice_id", "WWI Invoice ID", "integer"),
        Col("sale_quantity", "Sale Quantity", "integer", "measure", hidden=True),
        Col("sale_total_excluding_tax", "Sale Total Excluding Tax", "real", "measure", hidden=True),
        Col("sale_profit", "Sale Profit", "real", "measure", hidden=True),
        Col("sale_total_including_tax", "Sale Total Including Tax", "real", "measure", hidden=True),
    ],
    "Invoice lines (fact_sale), one row per line.",
)

ORDERS = Table(
    "orders", "Orders",
    "SELECT order_key AS ord_order_key, order_date AS ord_order_date, city_key AS ord_city_key, "
    "customer_key AS ord_customer_key, stock_item_key AS ord_stock_item_key, salesperson_key AS ord_salesperson_key, "
    "picker_key AS ord_picker_key, wwi_order_id AS ord_wwi_order_id, wwi_backorder_id AS ord_wwi_backorder_id, "
    "quantity AS ord_quantity, total_excluding_tax AS ord_total_excluding_tax FROM slc.wwi.fact_order",
    [
        Col("ord_order_key", "Order Key", "integer", hidden=True),
        Col("ord_order_date", "Order Date", "date", desc="Date the order was placed (the orders fact's primary date)."),
        Col("ord_city_key", "Order City Key", "integer", hidden=True),
        Col("ord_customer_key", "Order Customer Key", "integer", hidden=True),
        Col("ord_stock_item_key", "Order Stock Item Key", "integer", hidden=True),
        Col("ord_salesperson_key", "Order Salesperson Key", "integer", hidden=True),
        Col("ord_picker_key", "Order Picker Key", "integer", hidden=True),
        Col("ord_wwi_order_id", "WWI Order ID", "integer"),
        Col("ord_wwi_backorder_id", "WWI Backorder ID", "integer", hidden=True),
        Col("ord_quantity", "Order Quantity", "integer", "measure", hidden=True),
        Col("ord_total_excluding_tax", "Order Total Excluding Tax", "real", "measure", hidden=True),
    ],
    "Order lines (fact_order), one row per line.",
)

RLS_TERRITORY = Calc(
    "rls_wwi_territory", "RLS Territory Filter",
    f"NOT ISMEMBEROF('{TERRITORY_GROUP}') OR [ci_sales_territory] = 'Southeast'",
    "boolean", role="dimension", hidden=True,
    desc="Row-level security: members of the Southeast territory group see Southeast sales and orders only.",
)

WWI_SALES_ORDERS = DataSource(
    key="slc_wwi_sales_orders",
    name="SLC WWI Sales and Orders",
    caption="SLC WWI Sales and Orders",
    desc="WideWorldImporters sales and orders as a multi-fact relationship model over shared Date, Customer, City, "
         "Stock Item and Salesperson tables (W-S1, W-S2, W-M1, W-C1, B-W1 to B-W5).",
    tables=[
        SALES, ORDERS,
        date_table("date", "Date", "d_", "wwi", WWI_DATE_CAPTIONS, "Date",
                   "Shared calendar: invoice date for sales, order date for orders (fiscal year starts 1 November)."),
        date_table("delivery_date", "Delivery Date", "dd_", "wwi",
                   {"calendar_year": "Delivery Year", "month_start_date": "Delivery Month Start Date"},
                   "Delivery Date", "Delivery date role of the calendar (sales only)."),
        Table("customer", "Customer",
              "SELECT customer_key AS c_customer_key, wwi_customer_id AS c_wwi_customer_id, customer AS c_customer, "
              "category AS c_category, buying_group AS c_buying_group FROM slc.wwi.dim_customer",
              [Col("c_customer_key", "Customer Key", "integer", hidden=True),
               Col("c_wwi_customer_id", "WWI Customer ID", "integer"),
               Col("c_customer", "Customer", "string", desc=dim_desc("customer")),
               Col("c_category", "Customer Category", "string"),
               Col("c_buying_group", "Buying Group", "string")],
              "Customer as recorded at the time of the fact (shared by sales and orders)."),
        Table("bill_to_customer", "Bill-To Customer",
              "SELECT customer_key AS bc_customer_key, customer AS bc_customer FROM slc.wwi.dim_customer",
              [Col("bc_customer_key", "Bill-To Customer Key", "integer", hidden=True),
               Col("bc_customer", "Bill-To Customer", "string", desc=dim_desc("bill_to_customer"))],
              "Bill-to customer role of the customer dimension (sales only)."),
        Table("city", "City",
              "SELECT city_key AS ci_city_key, city AS ci_city, state_province AS ci_state_province, "
              "country AS ci_country, continent AS ci_continent, sales_territory AS ci_sales_territory, "
              "region AS ci_region, subregion AS ci_subregion FROM slc.wwi.dim_city",
              [Col("ci_city_key", "City Key", "integer", hidden=True),
               Col("ci_city", "City", "string", desc=dim_desc("city")),
               Col("ci_state_province", "State Province", "string"),
               Col("ci_country", "Country", "string"),
               Col("ci_continent", "Continent", "string"),
               Col("ci_sales_territory", "Sales Territory", "string",
                   desc="Sales territory of the city as recorded at the time of the fact; alternate hierarchy over State Province."),
               Col("ci_region", "Region", "string"),
               Col("ci_subregion", "Subregion", "string")],
              "Delivery city as recorded at the time of the fact (shared by sales and orders)."),
        STOCK_ITEM, CURRENT_STOCK_ITEM, STOCK_GROUP,
        Table("salesperson", "Salesperson",
              "SELECT employee_key AS sp_employee_key, employee AS sp_employee FROM slc.wwi.dim_employee",
              [Col("sp_employee_key", "Salesperson Key", "integer", hidden=True),
               Col("sp_employee", "Salesperson", "string", desc=dim_desc("salesperson"))],
              "Salesperson role of the employee dimension (shared by sales and orders)."),
        Table("picker", "Picker",
              "SELECT employee_key AS pk_employee_key, employee AS pk_employee FROM slc.wwi.dim_employee",
              [Col("pk_employee_key", "Picker Key", "integer", hidden=True),
               Col("pk_employee", "Picker", "string", desc=dim_desc("picker"))],
              "Picker role of the employee dimension (orders only)."),
    ],
    rels=[
        Rel("sales", "date", [("sale_invoice_date", "d_date_key")]),
        Rel("orders", "date", [("ord_order_date", "d_date_key")]),
        Rel("sales", "delivery_date", [("sale_delivery_date", "dd_date_key")]),
        Rel("sales", "customer", [("sale_customer_key", "c_customer_key")]),
        Rel("orders", "customer", [("ord_customer_key", "c_customer_key")]),
        Rel("sales", "bill_to_customer", [("sale_bill_to_customer_key", "bc_customer_key")]),
        Rel("sales", "city", [("sale_city_key", "ci_city_key")]),
        Rel("orders", "city", [("ord_city_key", "ci_city_key")]),
        Rel("sales", "stock_item", [("sale_stock_item_key", "si_stock_item_key")]),
        Rel("orders", "stock_item", [("ord_stock_item_key", "si_stock_item_key")]),
        Rel("stock_item", "current_stock_item", [("si_wwi_stock_item_id", "csi_wwi_stock_item_id")]),
        Rel("stock_item", "stock_group", [("si_wwi_stock_item_id", "sg_wwi_stock_item_id")]),
        Rel("sales", "salesperson", [("sale_salesperson_key", "sp_employee_key")]),
        Rel("orders", "salesperson", [("ord_salesperson_key", "sp_employee_key")]),
        Rel("orders", "picker", [("ord_picker_key", "pk_employee_key")]),
    ],
    calcs=[
        metric_calc("W-S1", "m_revenue", "SUM([sale_total_excluding_tax])"),
        metric_calc("B-W1", "m_revenue_including_tax", "SUM([sale_total_including_tax])"),
        metric_calc("B-W2", "m_gross_profit", "SUM([sale_profit])"),
        metric_calc("B-W3", "m_units_sold", "SUM([sale_quantity])", "integer"),
        metric_calc("B-W4", "m_invoice_count", "COUNTD([sale_wwi_invoice_id])", "integer"),
        metric_calc("W-M1", "m_gross_margin_pct", "SUM([sale_profit]) / SUM([sale_total_excluding_tax])"),
        metric_calc("W-S2", "m_ordered_quantity", "SUM([ord_quantity])", "integer"),
        metric_calc("B-W5", "m_backordered_order_lines",
                    "IF COUNT([ord_wwi_backorder_id]) > 0 THEN COUNT([ord_wwi_backorder_id]) END", "integer"),
        metric_calc("W-C1", "m_stock_group_revenue_share",
                    "SUM([sale_total_excluding_tax]) / MIN({EXCLUDE [sg_stock_group_name] : SUM([sale_total_excluding_tax])})",
                    extra="Denominator: revenue of the same context with Stock Group removed, counting each line once."),
        Calc("m_sales_line_count", "Sales Line Count", "COUNT([sale_key])", "integer",
             desc="Number of invoice lines in context (row presence of the sales fact).", fmt=FORMATS["count"]),
        Calc("m_order_line_count", "Order Line Count", "COUNT([ord_order_key])", "integer",
             desc="Number of order lines in context (row presence of the orders fact).", fmt=FORMATS["count"]),
        Calc("m_revenue_all_stock_groups", "Revenue (All Stock Groups)",
             "MIN({EXCLUDE [sg_stock_group_name] : SUM([sale_total_excluding_tax])})", "real",
             desc="Revenue of the current context with Stock Group removed; each invoice line counted once. "
                  "The denominator of Stock Group Revenue Share.", fmt=FORMATS["currency"]),
        RLS_TERRITORY,
    ],
    rls=[RlsFilter("rls_wwi_territory", False,
                   "References City (sales_territory); a filter on another table's field cannot be scoped to one "
                   "logical table, so it is pervasive: it restricts City and the tables related to it (Sales, Orders).")],
)

# =========================================================================== WWI stock

STOCK_DAILY = Table(
    "stock_daily", "Stock Daily",
    "SELECT h.snapshot_date AS stk_snapshot_date, h.wwi_stock_item_id AS stk_wwi_stock_item_id, "
    "h.stock_item_key AS stk_stock_item_key, h.quantity_on_hand AS stk_quantity_on_hand, "
    "h.balance_basis AS stk_balance_basis, "
    "SUM(s.units_sold) OVER (PARTITION BY h.wwi_stock_item_id ORDER BY h.snapshot_date "
    "ROWS BETWEEN 90 PRECEDING AND CURRENT ROW) AS stk_units_sold_91d "
    "FROM slc.wwi.fact_stock_holding_daily h "
    "LEFT JOIN (SELECT si.wwi_stock_item_id, f.invoice_date, SUM(f.quantity) AS units_sold "
    "FROM slc.wwi.fact_sale f JOIN slc.wwi.dim_stock_item si ON si.stock_item_key = f.stock_item_key "
    "GROUP BY si.wwi_stock_item_id, f.invoice_date) s "
    "ON s.wwi_stock_item_id = h.wwi_stock_item_id AND s.invoice_date = h.snapshot_date",
    [
        Col("stk_snapshot_date", "Snapshot Date", "date", desc="Date of the daily stock snapshot."),
        Col("stk_wwi_stock_item_id", "Snapshot Stock Item ID", "integer", hidden=True),
        Col("stk_stock_item_key", "Snapshot Stock Item Key", "integer", hidden=True),
        Col("stk_quantity_on_hand", "Quantity On Hand", "integer", "measure", hidden=True),
        Col("stk_balance_basis", "Balance Basis", "string",
            desc="How the daily balance was derived: holding_backcast or flow_min_opening (SPEC § 5.3 rule 6)."),
        Col("stk_units_sold_91d", "Item Units Sold 91 Days", "integer", "measure", hidden=True),
    ],
    "Dense daily stock snapshot per stock item, with the item's units sold in the 91 days ending on the snapshot date "
    "(the snapshot has one row per item per day, so 91 rows are 91 days).",
)

# Every non-date dimension of SLC WWI Stock. The period end d* is the last snapshot date of the view's period with these
# removed, so an item attribute in the view (an SCD2 color, a stock group) never moves d* (SPEC § 6.3 W-M2).
STOCK_NON_DATE_DIMS = ["si_wwi_stock_item_id", "si_stock_item", "si_brand", "si_color", "si_size", "si_selling_package",
                       "si_is_chiller_stock", "csi_stock_item", "csi_color", "sg_stock_group_name", "stk_balance_basis"]
PERIOD_END = ("{EXCLUDE " + ", ".join(f"[{d}]" for d in STOCK_NON_DATE_DIMS) + " : MAX([stk_snapshot_date])}")

WWI_STOCK = DataSource(
    key="slc_wwi_stock",
    name="SLC WWI Stock",
    caption="SLC WWI Stock",
    desc="WideWorldImporters daily stock holdings with trailing 91-day sales per item (W-M2, W-C2).",
    tables=[
        STOCK_DAILY,
        date_table("date", "Date", "d_", "wwi", WWI_DATE_CAPTIONS, "Date", "Calendar of the snapshot date."),
        STOCK_ITEM, CURRENT_STOCK_ITEM, STOCK_GROUP,
    ],
    rels=[
        Rel("stock_daily", "date", [("stk_snapshot_date", "d_date_key")]),
        Rel("stock_daily", "stock_item", [("stk_stock_item_key", "si_stock_item_key")]),
        Rel("stock_item", "current_stock_item", [("si_wwi_stock_item_id", "csi_wwi_stock_item_id")]),
        Rel("stock_item", "stock_group", [("si_wwi_stock_item_id", "sg_wwi_stock_item_id")]),
    ],
    calcs=[
        Calc("x_period_end", "Period End Snapshot Date", PERIOD_END, "date", role="dimension", hidden=True,
             desc="Last snapshot date of the period in context, ignoring item and group attributes in the view."),
        metric_calc("W-M2", "m_closing_stock",
                    "SUM(IF [stk_snapshot_date] = [x_period_end] THEN [stk_quantity_on_hand] END)",
                    extra="Value on the last snapshot date of the period in context."),
        Calc("m_units_sold_91d", "Units Sold Trailing 91 Days",
             "SUM(IF [stk_snapshot_date] = [x_period_end] THEN [stk_units_sold_91d] END)", "real",
             desc="Units sold in the 91 days ending on the last snapshot date of the period, for the items in "
                  "context; blank when no unit sold.", fmt=FORMATS["units"]),
        metric_calc("W-C2", "m_days_of_supply", "[m_closing_stock] / ([m_units_sold_91d] / 91)"),
        Calc("m_snapshot_rows", "Snapshot Row Count", "COUNT([stk_snapshot_date])", "integer",
             desc="Number of item-day snapshot rows in context (row presence of the stock fact).", fmt=FORMATS["count"]),
        Calc("m_closing_date", "Closing Snapshot Date", "MAX([x_period_end])", "date",
             desc="Last snapshot date of the period in context (the date closing stock is taken on)."),
        Calc("rls_wwi_inventory", "RLS Inventory Filter",
             f"NOT ISMEMBEROF('{TERRITORY_GROUP}') AND NOT ISNULL([stk_snapshot_date])", "boolean",
             role="dimension", hidden=True,
             desc="Row-level security: the Southeast territory group has no inventory access."),
    ],
    rls=[RlsFilter("rls_wwi_inventory", True,
                   "Scoped to the Stock Daily logical table: stock rows disappear for the territory group, so W-M2 and "
                   "W-C2 return blank, while item and group members stay browsable.")],
)

# =========================================================================== NYC trips

NYC_TRIPS = DataSource(
    key="slc_nyc_trips",
    name="SLC NYC Trips",
    caption="SLC NYC Trips",
    desc="NYC Yellow Taxi trips 2023-2024 with role-played pickup and dropoff zones (B-N1 to B-N5, N-S1 to N-C2).",
    tables=[
        Table("trips", "Trips",
              "SELECT t.trip_id AS trip_id, t.vendor_id AS trip_vendor_id, t.pickup_ts AS trip_pickup_ts, "
              "t.pickup_date AS trip_pickup_date, t.dropoff_date AS trip_dropoff_date, "
              "t.pickup_hour AS trip_pickup_hour, t.pu_location_id AS trip_pu_location_id, "
              "t.do_location_id AS trip_do_location_id, t.od_pair_id AS trip_od_pair_id, "
              "t.trip_distance AS trip_trip_distance, t.payment_type AS trip_payment_type, "
              "t.fare_amount AS trip_fare_amount, t.tip_amount AS trip_tip_amount, t.tolls_amount AS trip_tolls_amount, "
              "t.total_amount AS trip_total_amount, z.borough AS trip_rls_pickup_borough "
              "FROM slc.nyctaxi.fact_trip t LEFT JOIN slc.nyctaxi.dim_zone z ON z.location_id = t.pu_location_id",
              [Col("trip_id", "Trip ID", "integer", hidden=True),
               Col("trip_vendor_id", "Vendor", "integer", desc=dim_desc("vendor")),
               Col("trip_pickup_ts", "Pickup Timestamp", "datetime", desc="Pickup date and time (incremental extract key)."),
               Col("trip_pickup_date", "Pickup Date", "date", desc=dim_desc("pickup_date")),
               Col("trip_dropoff_date", "Dropoff Date", "date", desc=dim_desc("dropoff_date")),
               Col("trip_pickup_hour", "Pickup Hour", "integer", desc=dim_desc("pickup_hour")),
               Col("trip_pu_location_id", "Trip Pickup Location ID", "integer", hidden=True),
               Col("trip_do_location_id", "Trip Dropoff Location ID", "integer", hidden=True),
               Col("trip_od_pair_id", "OD Pair ID", "integer", hidden=True),
               Col("trip_trip_distance", "Trip Distance", "real", "measure", hidden=True),
               Col("trip_payment_type", "Trip Payment Type Code", "integer", hidden=True),
               Col("trip_fare_amount", "Trip Fare Amount", "real", "measure", hidden=True),
               Col("trip_tip_amount", "Trip Tip Amount", "real", "measure", hidden=True),
               Col("trip_tolls_amount", "Trip Tolls Amount", "real", "measure", hidden=True),
               Col("trip_total_amount", "Trip Total Amount", "real", "measure", hidden=True),
               Col("trip_rls_pickup_borough", "RLS Pickup Borough", "string", hidden=True)],
              "Valid Yellow Taxi trips (fact_trip) with the pickup borough attached for row-level security."),
        date_table("pickup_calendar", "Pickup Calendar", "pc_", "nyctaxi",
                   {"calendar_year": "Pickup Year", "calendar_quarter": "Pickup Quarter",
                    "calendar_month": "Pickup Calendar Month", "month_start_date": "Pickup Month Start Date",
                    "day_of_week": "Pickup Day of Week", "day_name": "Pickup Day Name"},
                   "Pickup Calendar Date", "Calendar of the pickup date (every day of 2023-2025, with or without trips)."),
        Table("pickup_zone", "Pickup Zone",
              "SELECT location_id AS pz_location_id, borough AS pz_borough, zone AS pz_zone, "
              "service_zone AS pz_service_zone FROM slc.nyctaxi.dim_zone",
              [Col("pz_location_id", "Pickup Zone ID", "integer"),
               Col("pz_borough", "Pickup Borough", "string", desc="Borough of the pickup zone."),
               Col("pz_zone", "Pickup Zone", "string", desc=dim_desc("pickup_zone")),
               Col("pz_service_zone", "Pickup Service Zone", "string")],
              "Pickup zone role of the TLC zone dimension."),
        Table("dropoff_zone", "Dropoff Zone",
              "SELECT location_id AS dz_location_id, borough AS dz_borough, zone AS dz_zone, "
              "service_zone AS dz_service_zone FROM slc.nyctaxi.dim_zone",
              [Col("dz_location_id", "Dropoff Zone ID", "integer"),
               Col("dz_borough", "Dropoff Borough", "string", desc="Borough of the dropoff zone."),
               Col("dz_zone", "Dropoff Zone", "string", desc=dim_desc("dropoff_zone")),
               Col("dz_service_zone", "Dropoff Service Zone", "string")],
              "Dropoff zone role of the TLC zone dimension."),
        Table("payment_type", "Payment Type",
              "SELECT payment_type AS pt_payment_type, payment_type_name AS pt_payment_type_name "
              "FROM slc.nyctaxi.dim_payment_type",
              [Col("pt_payment_type", "Payment Type Code", "integer"),
               Col("pt_payment_type_name", "Payment Type", "string", desc=dim_desc("payment_type"))],
              "TLC payment type codes and labels."),
    ],
    rels=[
        Rel("trips", "pickup_calendar", [("trip_pickup_date", "pc_date_key")]),
        Rel("trips", "pickup_zone", [("trip_pu_location_id", "pz_location_id")]),
        Rel("trips", "dropoff_zone", [("trip_do_location_id", "dz_location_id")]),
        Rel("trips", "payment_type", [("trip_payment_type", "pt_payment_type")]),
    ],
    params=[Param("p_as_of_date", "As-of Date", "date", "#2024-12-31#",
                  "Anchor date for year-to-date, same-time-last-year and month-to-date measures.")],
    calcs=[
        Calc("dropoff_year", "Dropoff Year", "YEAR([trip_dropoff_date])", "integer", role="dimension",
             desc="Calendar year of the dropoff date."),
        Calc("dropoff_month_start", "Dropoff Month Start Date", "DATE(DATETRUNC('month', [trip_dropoff_date]))", "date",
             role="dimension", desc="First day of the dropoff month."),
        metric_calc("B-N1", "m_trip_count", "COUNT([trip_id])", "integer"),
        metric_calc("B-N2", "m_total_trip_distance", "SUM([trip_trip_distance])"),
        metric_calc("B-N3", "m_fare_amount", "SUM([trip_fare_amount])"),
        metric_calc("B-N4", "m_tip_amount", "SUM([trip_tip_amount])"),
        metric_calc("B-N5", "m_tolls_amount", "SUM([trip_tolls_amount])"),
        metric_calc("N-S1", "m_gross_trip_revenue", "SUM([trip_total_amount])"),
        metric_calc("N-S2", "m_card_tips", "SUM(IF [trip_payment_type] = 1 THEN [trip_tip_amount] END)"),
        metric_calc("N-M1", "m_distinct_od_pairs", "COUNTD([trip_od_pair_id])", "integer"),
        metric_calc("N-M2", "m_fare_per_mile", "SUM([trip_fare_amount]) / SUM([trip_trip_distance])"),
        Calc("m_revenue_ytd", "Revenue YTD",
             "SUM(IF [trip_pickup_date] >= DATE(DATETRUNC('year', [p_as_of_date])) "
             "AND [trip_pickup_date] <= [p_as_of_date] THEN [trip_total_amount] END)",
             "real", desc=metric_desc("N-C1", "Year-to-date through the As-of Date parameter."), fmt=FORMATS["currency"],
             metric_id="N-C1"),
        Calc("m_revenue_stly_ytd", "Revenue YTD Same Time Last Year",
             "SUM(IF [trip_pickup_date] >= DATE(DATEADD('year', -1, DATETRUNC('year', [p_as_of_date]))) "
             "AND [trip_pickup_date] <= DATE(DATEADD('year', -1, [p_as_of_date])) THEN [trip_total_amount] END)",
             "real", desc="Revenue YTD one year before the As-of Date (29 February maps to 28 February).",
             fmt=FORMATS["currency"]),
        Calc("m_revenue_yoy_pct", "Revenue YoY % vs STLY",
             "([m_revenue_ytd] - [m_revenue_stly_ytd]) / [m_revenue_stly_ytd]", "real",
             desc="Year-over-year change of Revenue YTD against the same period last year.",
             fmt=FORMATS["ratio_pct"]),
        Calc("m_trips_mtd", "Trips MTD",
             "SUM(IF [trip_pickup_date] >= DATE(DATETRUNC('month', [p_as_of_date])) "
             "AND [trip_pickup_date] <= [p_as_of_date] THEN 1 END)", "integer",
             desc="Trips from the first day of the As-of Date's month through the As-of Date.", fmt=FORMATS["count"]),
        Calc("m_trips_ytd", "Trips YTD",
             "SUM(IF [trip_pickup_date] >= DATE(DATETRUNC('year', [p_as_of_date])) "
             "AND [trip_pickup_date] <= [p_as_of_date] THEN 1 END)", "integer",
             desc="Trips from 1 January of the As-of Date's year through the As-of Date.", fmt=FORMATS["count"]),
        Calc("as_of_day_of_month", "As-of Day of Month", "DAY([p_as_of_date])", "integer", role="dimension",
             desc="Calendar days elapsed in the As-of Date's month."),
        Calc("as_of_day_of_year", "As-of Day of Year", "DATEPART('dayofyear', [p_as_of_date])", "integer",
             role="dimension", desc="Calendar days elapsed in the As-of Date's year."),
        Calc("m_pace_index", METRICS["N-C2"]["display_name"],
             "(ZN([m_trips_mtd]) / DAY([p_as_of_date])) / ([m_trips_ytd] / DATEPART('dayofyear', [p_as_of_date]))",
             "real", desc=metric_desc("N-C2", "Anchored on the As-of Date parameter."), fmt=FORMATS["index"],
             metric_id="N-C2"),
        Calc("rls_nyc_pickup", "RLS Pickup Borough Filter",
             f"NOT ISMEMBEROF('{PICKUP_GROUP}') OR [trip_rls_pickup_borough] = 'Manhattan'", "boolean",
             role="dimension", hidden=True,
             desc="Row-level security: the Manhattan pickup group sees trips picked up in Manhattan only."),
    ],
    rls=[RlsFilter("rls_nyc_pickup", True,
                   "Scoped to the Trips logical table: the pickup borough travels on the trip row, so dropoff (and "
                   "pickup) zone members stay browsable while every trip measure reflects Manhattan pickups only.")],
    incremental_key="trip_pickup_ts",
)

DATASOURCES = [WWI_SALES_ORDERS, WWI_STOCK, NYC_TRIPS]
BY_NAME = {ds.name: ds for ds in DATASOURCES}
BY_KEY = {ds.key: ds for ds in DATASOURCES}
