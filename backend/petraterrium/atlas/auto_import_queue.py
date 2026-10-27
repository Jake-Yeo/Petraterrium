from datetime import date
from typing import Literal

from pydantic import Field

from ..contracts import Contract
from .database import FIELDS, AtlasStore
from .hierarchy_queue import (
    LEVEL_ORDER,
    _country_aggregates,
    _create_hierarchy_coverage,
    _region_aggregates,
)
from .organizer import resolve

QueueLevel = Literal["region", "country", "city"]
QueueSort = Literal["impact", "hierarchy", "population"]
CityBatch = Literal["primary", "low_priority", "all"]


class AutoImportQueueItem(Contract):
    target_id: str
    level: QueueLevel
    place_key: str
    place_label: str
    country_code: str | None = None
    geonameid: int | None = None
    feature: str
    current_status: Literal["missing", "inherited", "imputed"]
    population: int = Field(ge=0)
    missing_impact: int = Field(ge=0)
    weight_source: str
    place_item_count: int = Field(ge=1)


class AutoImportQueuePage(Contract):
    items: list[AutoImportQueueItem]
    filtered_count: int = Field(ge=0)
    selected_population: int = Field(ge=0)
    primary_count: int = Field(ge=0)
    primary_population: int = Field(ge=0)
    low_priority_count: int = Field(ge=0)
    low_priority_population: int = Field(ge=0)
    city_population_threshold: int | None = Field(default=1_000_000, ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    scope: str
    as_of: str
    revision: int = Field(ge=0)


def _target_id(level: str, place_key: str, feature: str) -> str:
    return f"{level}|{place_key}|{feature}"


def _aggregate_items(aggregates, fields: tuple[str, ...]) -> list[AutoImportQueueItem]:
    items = []
    for aggregate in aggregates.values():
        place_key = (
            aggregate.label
            if aggregate.level == "region"
            else aggregate.country_code or aggregate.label
        )
        missing_features = [
            feature for feature in fields if aggregate.counts_by_field[feature]["missing"] > 0
        ]
        for feature in missing_features:
            missing_count = aggregate.counts_by_field[feature]["missing"]
            if missing_count <= 0:
                continue
            impact = round(max(0, aggregate.population_by_field[feature]["missing"]))
            items.append(
                AutoImportQueueItem(
                    target_id=_target_id(aggregate.level, place_key, feature),
                    level=aggregate.level,
                    place_key=place_key,
                    place_label=aggregate.label,
                    country_code=aggregate.country_code,
                    feature=feature,
                    current_status="missing",
                    population=aggregate.population,
                    missing_impact=impact,
                    weight_source=aggregate.weight_source,
                    place_item_count=len(missing_features),
                )
            )
    return items


def _city_items(
    conn,
    fields: tuple[str, ...],
    threshold: int | None,
    city_batch: CityBatch,
    search: str,
    limit: int,
) -> tuple[list[AutoImportQueueItem], int, int, int, int, int, int]:
    field_rows = " UNION ALL ".join("SELECT ? field" for _ in fields)
    clauses = ["r.field IS NULL"]
    parameters: list[str | int] = [*fields]
    term = search.strip()
    if term:
        escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        clauses.append(
            "(c.name LIKE ? ESCAPE '\\' COLLATE NOCASE OR "
            "c.asciiname LIKE ? ESCAPE '\\' COLLATE NOCASE OR "
            "c.country_code=? COLLATE NOCASE OR CAST(c.geonameid AS TEXT)=? OR "
            "f.field LIKE ? ESCAPE '\\' COLLATE NOCASE)"
        )
        parameters.extend(
            (f"%{escaped}%", f"%{escaped}%", term, term, f"%{escaped}%")
        )
    if threshold is not None and city_batch == "primary":
        clauses.append("c.population>=?")
        parameters.append(threshold)
    elif threshold is not None and city_batch == "low_priority":
        clauses.append("c.population<?")
        parameters.append(threshold)
    base = f"""FROM cities c CROSS JOIN ({field_rows}) f LEFT JOIN resolved r
        ON r.geonameid=c.geonameid AND r.field=f.field
        WHERE {' AND '.join(clauses)}"""
    rows = conn.execute(
        f"""SELECT c.geonameid,c.name,c.country_code,c.population,f.field,
        COUNT(*) OVER(PARTITION BY c.geonameid) place_item_count {base}
        ORDER BY c.population DESC,c.name COLLATE NOCASE,c.geonameid,f.field LIMIT ?""",
        [*parameters, limit],
    ).fetchall()
    stats = conn.execute(
        f"""SELECT COALESCE(SUM(missing_fields),0) item_count,
        COALESCE(SUM(population),0) population FROM (
        SELECT c.geonameid,c.population,COUNT(*) missing_fields {base}
        GROUP BY c.geonameid,c.population)""",
        parameters,
    ).fetchone()

    def cohort_stats(operator: str):
        if threshold is None:
            return stats
        cohort_parameters: list[str | int] = [*fields]
        cohort_clauses = ["r.field IS NULL", f"c.population{operator}?"]
        cohort_parameters.append(threshold)
        if term:
            cohort_clauses.append(
                "(c.name LIKE ? ESCAPE '\\' COLLATE NOCASE OR "
                "c.asciiname LIKE ? ESCAPE '\\' COLLATE NOCASE OR "
                "c.country_code=? COLLATE NOCASE OR CAST(c.geonameid AS TEXT)=? OR "
                "f.field LIKE ? ESCAPE '\\' COLLATE NOCASE)"
            )
            cohort_parameters.extend(
                (f"%{escaped}%", f"%{escaped}%", term, term, f"%{escaped}%")
            )
        cohort_base = f"""FROM cities c CROSS JOIN ({field_rows}) f LEFT JOIN resolved r
        ON r.geonameid=c.geonameid AND r.field=f.field
        WHERE {' AND '.join(cohort_clauses)}"""
        return conn.execute(
            f"""SELECT COALESCE(SUM(missing_fields),0) item_count,
            COALESCE(SUM(population),0) population FROM (
            SELECT c.geonameid,c.population,COUNT(*) missing_fields {cohort_base}
            GROUP BY c.geonameid,c.population)""",
            cohort_parameters,
        ).fetchone()

    primary = cohort_stats(">=")
    low_priority = cohort_stats("<")
    return (
        [
            AutoImportQueueItem(
                target_id=_target_id("city", str(row["geonameid"]), row["field"]),
                level="city",
                place_key=str(row["geonameid"]),
                place_label=row["name"],
                country_code=row["country_code"],
                geonameid=row["geonameid"],
                feature=row["field"],
                current_status="missing",
                population=row["population"],
                missing_impact=row["population"],
                weight_source="GeoNames cities500 population",
                place_item_count=row["place_item_count"],
            )
            for row in rows
        ],
        stats["item_count"],
        stats["population"],
        primary["item_count"],
        primary["population"],
        low_priority["item_count"],
        low_priority["population"],
    )


def auto_import_queue(
    store: AtlasStore,
    scope: str = "shared",
    as_of: str | None = None,
    levels: tuple[QueueLevel, ...] = ("region", "country", "city"),
    features: tuple[str, ...] = FIELDS,
    search: str = "",
    sort: QueueSort = "impact",
    city_population_threshold: int | None = 1_000_000,
    city_batch: CityBatch = "primary",
    page: int = 1,
    page_size: int = 100,
) -> AutoImportQueuePage:
    if not levels or any(level not in LEVEL_ORDER for level in levels):
        raise ValueError("Choose at least one valid hierarchy level")
    if not features or any(feature not in FIELDS for feature in features):
        raise ValueError("Choose at least one canonical marginal feature")
    if len(features) != len(set(features)):
        raise ValueError("Queue features must be unique")
    if page < 1 or not 1 <= page_size <= 500:
        raise ValueError("Invalid queue page")
    if city_population_threshold is not None and city_population_threshold < 0:
        raise ValueError("City population threshold cannot be negative")
    selected_date = as_of or date.today().isoformat()
    with store.connection() as conn:
        conn.execute("BEGIN")
        resolve(conn, scope, selected_date, features)
        _create_hierarchy_coverage(conn, features)
        countries = _country_aggregates(conn, features)
        regions = _region_aggregates(countries, features)
        items = []
        if "region" in levels and city_batch != "low_priority":
            items.extend(_aggregate_items(regions, features))
        if "country" in levels and city_batch != "low_priority":
            items.extend(_aggregate_items(countries, features))
        term = search.casefold().strip()
        if term:
            items = [
                item
                for item in items
                if term in item.place_label.casefold()
                or term in item.feature.casefold()
                or term == (item.country_code or "").casefold()
            ]
        aggregate_items = list(items)
        city_count = 0
        city_population = 0
        primary_city_count = 0
        primary_city_population = 0
        low_priority_count = 0
        low_priority_population = 0
        if "city" in levels:
            (
                city_items,
                city_count,
                city_population,
                primary_city_count,
                primary_city_population,
                low_priority_count,
                low_priority_population,
            ) = _city_items(
                conn,
                features,
                city_population_threshold,
                city_batch,
                search,
                page * page_size + len(aggregate_items),
            )
            items.extend(city_items)
        if sort == "hierarchy":
            items.sort(
                key=lambda item: (
                    LEVEL_ORDER[item.level],
                    -item.missing_impact,
                    item.place_label.casefold(),
                    item.feature,
                )
            )
        elif sort == "impact":
            items.sort(
                key=lambda item: (
                    -item.missing_impact,
                    LEVEL_ORDER[item.level],
                    item.place_label.casefold(),
                    item.feature,
                )
            )
        else:
            items.sort(
                key=lambda item: (
                    -item.population,
                    LEVEL_ORDER[item.level],
                    -item.missing_impact,
                    item.place_label.casefold(),
                    item.feature,
                )
            )
        aggregate_population = sum(
            {
                (item.level, item.place_key): item.population for item in aggregate_items
            }.values()
        )
        count = len(aggregate_items) + city_count
        selected_population = aggregate_population + city_population
        start = (page - 1) * page_size
        return AutoImportQueuePage(
            items=items[start : start + page_size],
            filtered_count=count,
            selected_population=selected_population,
            primary_count=len(aggregate_items) + primary_city_count,
            primary_population=aggregate_population + primary_city_population,
            low_priority_count=low_priority_count,
            low_priority_population=low_priority_population,
            city_population_threshold=city_population_threshold,
            page=page,
            page_size=page_size,
            scope=scope,
            as_of=selected_date,
            revision=store.revision(conn),
        )
