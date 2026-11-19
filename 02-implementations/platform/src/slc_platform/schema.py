"""Canonical gold schemas (SPEC § 5). Single source of truth for column names and types.

Each table is an ordered list of (column, spark_sql_type, nullable). Pipelines
render these into the `schema=` DDL of their datasets; tests compare transform
output and SPEC § 5 against them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

Column = tuple[str, str, bool]

DATE_COLUMNS: list[Column] = [
    ("date_key", "DATE", False),
    ("calendar_year", "SMALLINT", False),
    ("calendar_quarter", "TINYINT", False),
    ("calendar_month", "TINYINT", False),
    ("month_name", "STRING", False),
    ("month_start_date", "DATE", False),
    ("day_of_month", "TINYINT", False),
    ("day_of_year", "SMALLINT", False),
    ("day_of_week", "TINYINT", False),
    ("day_name", "STRING", False),
    ("iso_week_number", "TINYINT", False),
    ("fiscal_year", "SMALLINT", False),
    ("fiscal_quarter", "TINYINT", False),
    ("fiscal_month", "TINYINT", False),
    ("fiscal_period_index", "INT", False),
    ("day_of_fiscal_year", "SMALLINT", False),
]

SCD2_COLUMNS: list[Column] = [
    ("valid_from", "TIMESTAMP", False),
    ("valid_to", "TIMESTAMP", False),
    ("is_current", "BOOLEAN", False),
]


@dataclass(frozen=True)
class Table:
    name: str
    columns: list[Column]
    primary_key: tuple[str, ...] = ()
    foreign_keys: tuple[tuple[str, str, str], ...] = ()  # (column, parent_table, parent_column)
    exposed: bool = True
    comment: str = ""
    cluster_by: tuple[str, ...] = field(default_factory=tuple)

    @property
    def column_names(self) -> list[str]:
        return [c[0] for c in self.columns]

    def ddl(self, schema: str) -> str:
        """Render the dataset schema DDL with informational constraints (RELY)."""
        parts = [f"{n} {t}{'' if nullable else ' NOT NULL'}" for n, t, nullable in self.columns]
        if self.primary_key:
            parts.append(
                f"CONSTRAINT pk_{self.name} PRIMARY KEY ({', '.join(self.primary_key)}) RELY"
            )
        for col, parent, parent_col in self.foreign_keys:
            parts.append(
                f"CONSTRAINT fk_{self.name}_{col} FOREIGN KEY ({col}) "
                f"REFERENCES {schema}.{parent} ({parent_col}) RELY"
            )
        return ",\n".join(parts)


# --------------------------------------------------------------------- WWI

WWI_TABLES: dict[str, Table] = {
    t.name: t
    for t in [
        Table(
            "dim_date", DATE_COLUMNS, primary_key=("date_key",),
            comment="Generated gap-free calendar, 2013-2016, fiscal year starting 1 November.",
        ),
        Table(
            "dim_stock_item",
            [
                ("stock_item_key", "INT", False),
                ("wwi_stock_item_id", "INT", False),
                ("stock_item", "STRING", False),
                ("brand", "STRING", False),
                ("color", "STRING", False),
                ("size", "STRING", False),
                ("selling_package", "STRING", False),
                ("is_chiller_stock", "BOOLEAN", False),
                ("unit_price", "DECIMAL(18,2)", False),
                *SCD2_COLUMNS,
            ],
            primary_key=("stock_item_key",),
            comment="Stock item SCD Type 2 versions from [Dimension].[Stock Item].",
        ),
        Table(
            "dim_stock_group",
            [("stock_group_id", "INT", False), ("stock_group_name", "STRING", False)],
            primary_key=("stock_group_id",),
            comment="Stock groups from OLTP [Warehouse].[StockGroups].",
        ),
        Table(
            "bridge_stock_item_group",
            [("wwi_stock_item_id", "INT", False), ("stock_group_id", "INT", False)],
            primary_key=("wwi_stock_item_id", "stock_group_id"),
            foreign_keys=(("stock_group_id", "dim_stock_group", "stock_group_id"),),
            comment="Many-to-many stock item to stock group bridge on the durable item key.",
        ),
        Table(
            "dim_customer",
            [
                ("customer_key", "INT", False),
                ("wwi_customer_id", "INT", False),
                ("customer", "STRING", False),
                ("bill_to_customer", "STRING", False),
                ("category", "STRING", False),
                ("buying_group", "STRING", False),
                *SCD2_COLUMNS,
            ],
            primary_key=("customer_key",),
            comment="Customer SCD Type 2 versions; role-played as Customer and Bill-To Customer.",
        ),
        Table(
            "dim_city",
            [
                ("city_key", "INT", False),
                ("wwi_city_id", "INT", False),
                ("city", "STRING", False),
                ("state_province", "STRING", False),
                ("country", "STRING", False),
                ("continent", "STRING", False),
                ("sales_territory", "STRING", False),
                ("region", "STRING", False),
                ("subregion", "STRING", False),
                *SCD2_COLUMNS,
            ],
            primary_key=("city_key",),
            comment="City SCD Type 2 versions from [Dimension].[City].",
        ),
        Table(
            "dim_employee",
            [
                ("employee_key", "INT", False),
                ("wwi_employee_id", "INT", False),
                ("employee", "STRING", False),
                ("is_salesperson", "BOOLEAN", False),
                *SCD2_COLUMNS,
            ],
            primary_key=("employee_key",),
            comment="Employee SCD Type 2 versions; role-played as Salesperson and Picker.",
        ),
        Table(
            "fact_sale",
            [
                ("sale_key", "BIGINT", False),
                ("invoice_date", "DATE", False),
                ("delivery_date", "DATE", True),
                ("city_key", "INT", False),
                ("customer_key", "INT", False),
                ("bill_to_customer_key", "INT", False),
                ("stock_item_key", "INT", False),
                ("salesperson_key", "INT", False),
                ("wwi_invoice_id", "INT", False),
                ("quantity", "INT", False),
                ("unit_price", "DECIMAL(18,2)", False),
                ("total_excluding_tax", "DECIMAL(18,2)", False),
                ("tax_amount", "DECIMAL(18,2)", False),
                ("profit", "DECIMAL(18,2)", False),
                ("total_including_tax", "DECIMAL(18,2)", False),
            ],
            primary_key=("sale_key",),
            foreign_keys=(
                ("invoice_date", "dim_date", "date_key"),
                ("delivery_date", "dim_date", "date_key"),
                ("city_key", "dim_city", "city_key"),
                ("customer_key", "dim_customer", "customer_key"),
                ("bill_to_customer_key", "dim_customer", "customer_key"),
                ("stock_item_key", "dim_stock_item", "stock_item_key"),
                ("salesperson_key", "dim_employee", "employee_key"),
            ),
            cluster_by=("invoice_date",),
            comment="Invoice line grain from [Fact].[Sale].",
        ),
        Table(
            "fact_order",
            [
                ("order_key", "BIGINT", False),
                ("order_date", "DATE", False),
                ("city_key", "INT", False),
                ("customer_key", "INT", False),
                ("stock_item_key", "INT", False),
                ("salesperson_key", "INT", False),
                ("picker_key", "INT", True),
                ("wwi_order_id", "INT", False),
                ("wwi_backorder_id", "INT", True),
                ("quantity", "INT", False),
                ("total_excluding_tax", "DECIMAL(18,2)", False),
            ],
            primary_key=("order_key",),
            foreign_keys=(
                ("order_date", "dim_date", "date_key"),
                ("city_key", "dim_city", "city_key"),
                ("customer_key", "dim_customer", "customer_key"),
                ("stock_item_key", "dim_stock_item", "stock_item_key"),
                ("salesperson_key", "dim_employee", "employee_key"),
                ("picker_key", "dim_employee", "employee_key"),
            ),
            cluster_by=("order_date",),
            comment="Order line grain from [Fact].[Order].",
        ),
        Table(
            "fact_stock_movement",
            [
                ("movement_key", "BIGINT", False),
                ("movement_date", "DATE", False),
                ("stock_item_key", "INT", False),
                ("transaction_type_key", "INT", False),
                ("quantity", "INT", False),
            ],
            primary_key=("movement_key",),
            foreign_keys=(
                ("movement_date", "dim_date", "date_key"),
                ("stock_item_key", "dim_stock_item", "stock_item_key"),
            ),
            comment="Signed stock movements from [Fact].[Movement].",
        ),
        Table(
            "stock_holding_current",
            [("stock_item_key", "INT", False), ("quantity_on_hand", "INT", False)],
            primary_key=("stock_item_key",),
            exposed=False,
            comment="Build input only: current holding from [Fact].[Stock Holding].",
        ),
        Table(
            "fact_stock_holding_daily",
            [
                ("snapshot_date", "DATE", False),
                ("wwi_stock_item_id", "INT", False),
                ("stock_item_key", "INT", False),
                ("quantity_on_hand", "INT", False),
                ("balance_basis", "STRING", False),
            ],
            primary_key=("wwi_stock_item_id", "snapshot_date"),
            foreign_keys=(
                ("snapshot_date", "dim_date", "date_key"),
                ("stock_item_key", "dim_stock_item", "stock_item_key"),
            ),
            cluster_by=("snapshot_date",),
            comment="Dense daily stock snapshot derived per SPEC § 5.3 rule 6.",
        ),
    ]
}

# --------------------------------------------------------------------- NYC

TRIP_COLUMNS: list[Column] = [
    ("trip_id", "BIGINT", False),
    ("vendor_id", "INT", False),
    ("pickup_ts", "TIMESTAMP_NTZ", False),
    ("dropoff_ts", "TIMESTAMP_NTZ", False),
    ("pickup_date", "DATE", False),
    ("dropoff_date", "DATE", False),
    ("pickup_hour", "TINYINT", False),
    ("pu_location_id", "INT", False),
    ("do_location_id", "INT", False),
    ("od_pair_id", "INT", False),
    ("passenger_count", "INT", True),
    ("trip_distance", "DECIMAL(9,2)", False),
    ("payment_type", "INT", False),
    ("fare_amount", "DECIMAL(10,2)", False),
    ("tip_amount", "DECIMAL(10,2)", False),
    ("tolls_amount", "DECIMAL(10,2)", False),
    ("total_amount", "DECIMAL(10,2)", False),
]

NYC_TABLES: dict[str, Table] = {
    t.name: t
    for t in [
        Table(
            "dim_date", DATE_COLUMNS, primary_key=("date_key",),
            comment="Generated gap-free calendar, 2023-2025; role-played as Pickup and Dropoff Date.",
        ),
        Table(
            "dim_zone",
            [
                ("location_id", "INT", False),
                ("borough", "STRING", False),
                ("zone", "STRING", False),
                ("service_zone", "STRING", False),
            ],
            primary_key=("location_id",),
            comment="TLC taxi zones; role-played as Pickup Zone and Dropoff Zone.",
        ),
        Table(
            "dim_payment_type",
            [("payment_type", "INT", False), ("payment_type_name", "STRING", False)],
            primary_key=("payment_type",),
            comment="TLC Yellow Taxi payment type codes 0-6.",
        ),
        Table(
            "fact_trip",
            TRIP_COLUMNS,
            primary_key=("trip_id",),
            foreign_keys=(
                ("pickup_date", "dim_date", "date_key"),
                ("dropoff_date", "dim_date", "date_key"),
                ("pu_location_id", "dim_zone", "location_id"),
                ("do_location_id", "dim_zone", "location_id"),
                ("payment_type", "dim_payment_type", "payment_type"),
            ),
            cluster_by=("pickup_date",),
            comment="Valid Yellow Taxi trips, pickups 2023-01-01 to 2024-12-31 (SPEC § 5.3 rule 1).",
        ),
        Table(
            "fact_trip_quarantine",
            # Rejected rows can carry NULLs in any source column.
            [("trip_id", "BIGINT", True)]
            + [(n, t, True) for n, t, _ in TRIP_COLUMNS[1:]]
            + [("reject_reason", "STRING", False)],
            exposed=False,
            comment="Rows failing the valid trip predicate, with the first failed rule.",
        ),
    ]
}

# Calendar ranges (SPEC § 5.4): full calendar years spanning every fact date value.
WWI_CALENDAR = ("2013-01-01", "2016-12-31")
NYC_CALENDAR = ("2023-01-01", "2025-12-31")

# Source windows.
WWI_SNAPSHOT_WINDOW = ("2013-01-01", "2016-05-31")
NYC_PICKUP_WINDOW = ("2023-01-01", "2024-12-31")
