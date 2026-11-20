"""Constructors for VizQL Data Service query objects (OpenAPI 20263.0, schemas/vendor) and output typing.

Every field carries a fieldAlias: VDS returns OBJECTS keyed by alias, and the alias is the column name the assembly SQL
and the reconciliation runner read. Output types are derived from the published data source model so the runner can
load VDS results into typed tables.
"""

from __future__ import annotations

from model import BY_NAME, Calc, Col, Param

DUCK_TYPES = {"string": "VARCHAR", "integer": "BIGINT", "real": "DOUBLE", "date": "DATE", "datetime": "TIMESTAMP",
              "boolean": "BOOLEAN"}


def dim(caption: str, alias: str, sort: int | None = None, desc: bool = False) -> dict:
    f = {"fieldCaption": caption, "fieldAlias": alias}
    if sort is not None:
        f["sortPriority"] = sort
        f["sortDirection"] = "DESC" if desc else "ASC"
    return f


def agg(caption: str, alias: str, sort: int | None = None, desc: bool = False) -> dict:
    """An aggregate calculated field of the data source (function AGG)."""
    f = {"fieldCaption": caption, "fieldAlias": alias, "function": "AGG"}
    if sort is not None:
        f["sortPriority"] = sort
        f["sortDirection"] = "DESC" if desc else "ASC"
    return f


def calc(caption: str, formula: str, alias: str, datatype: str) -> tuple[dict, str]:
    """An ad hoc VDS calculation; returns (field, datatype) so the output type is declared explicitly."""
    return {"fieldCaption": caption, "calculation": formula, "fieldAlias": alias}, datatype


def in_set(caption: str, values: list, exclude: bool = False) -> dict:
    f = {"field": {"fieldCaption": caption}, "filterType": "SET", "values": values}
    if exclude:
        f["exclude"] = True
    return f


def num_range(caption: str, lo: float | None = None, hi: float | None = None) -> dict:
    if lo is not None and hi is not None:
        return {"field": {"fieldCaption": caption}, "filterType": "QUANTITATIVE_NUMERICAL",
                "quantitativeFilterType": "RANGE", "min": lo, "max": hi}
    if lo is not None:
        return {"field": {"fieldCaption": caption}, "filterType": "QUANTITATIVE_NUMERICAL",
                "quantitativeFilterType": "MIN", "min": lo}
    return {"field": {"fieldCaption": caption}, "filterType": "QUANTITATIVE_NUMERICAL",
            "quantitativeFilterType": "MAX", "max": hi}


def agg_min(caption: str, lo: float) -> dict:
    """Filter on an aggregate calculated field (HAVING semantics)."""
    return {"field": {"fieldCaption": caption, "function": "AGG"}, "filterType": "QUANTITATIVE_NUMERICAL",
            "quantitativeFilterType": "MIN", "min": lo}


def date_range(caption: str, lo: str, hi: str) -> dict:
    return {"field": {"fieldCaption": caption}, "filterType": "QUANTITATIVE_DATE",
            "quantitativeFilterType": "RANGE", "minDate": lo, "maxDate": hi}


def match(caption: str, equals: str) -> dict:
    """Exact string match expressed as a one-value SET filter."""
    return in_set(caption, [equals])


def query(datasource: str, fields: list, filters: list | None = None, parameters: dict | None = None) -> dict:
    """A query spec: {datasource, query, parameters, output}. fields may mix dicts and (dict, datatype) tuples."""
    ds = BY_NAME[datasource]
    model_fields = ds.fields()
    out_fields, output = [], {}
    for item in fields:
        f, datatype = item if isinstance(item, tuple) else (item, None)
        if datatype is None:
            target = model_fields.get(f["fieldCaption"])
            if target is None:
                raise KeyError(f"{datasource}: no field {f['fieldCaption']!r}")
            datatype = target.datatype if isinstance(target, (Col, Calc, Param)) else "string"
        out_fields.append(f)
        output[f["fieldAlias"]] = DUCK_TYPES[datatype]
    spec = {"datasource": datasource, "query": {"fields": out_fields}}
    if filters:
        spec["query"]["filters"] = filters
    if parameters:
        spec["query"]["parameters"] = [{"parameterCaption": k, "value": v} for k, v in parameters.items()]
    spec["output"] = output
    return spec
