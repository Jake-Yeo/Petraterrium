from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from pydantic import Field

from ..contracts import Contract
from .database import FIELDS, AtlasStore
from .organizer import resolve
from .regions import CANONICAL_REGIONS, country_region

HierarchyLevel = Literal["region", "country", "city"]
HierarchyCoverageState = Literal["no_data", "partial", "imputed_only", "complete"]

STATUS_ORDER = {"no_data": 0, "partial": 1, "imputed_only": 2, "complete": 3}
LEVEL_ORDER = {"region": 0, "country": 1, "city": 2}


class HierarchyCoverageCounts(Contract):
    present: int = Field(ge=0)
    inherited: int = Field(ge=0)
    imputed: int = Field(ge=0)
    missing: int = Field(ge=0)


class HierarchyBrowserRow(Contract):
    row_id: str
    parent_id: str | None = None
    level: HierarchyLevel
    label: str
    country_code: str | None = None
    geonameid: int | None = None
    population: int = Field(ge=0)
    city_count: int = Field(ge=0)
    measured_coverage_percent: float = Field(ge=0, le=100)
    effective_coverage_percent: float = Field(ge=0, le=100)
    counts: HierarchyCoverageCounts
    status: HierarchyCoverageState
    missing_fields: list[str]
    missing_field_count: int = Field(ge=0)
    missing_impact: int = Field(ge=0)
    weight_source: str
    has_children: bool = False


class HierarchyBreadcrumb(Contract):
    label: str
    level: HierarchyLevel
    parent_id: str | None = None


class HierarchyBrowserPage(Contract):
    level: HierarchyLevel
    parent_id: str | None = None
    rows: list[HierarchyBrowserRow]
    queue: list[HierarchyBrowserRow]
    breadcrumbs: list[HierarchyBreadcrumb]
    filtered_count: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    scope: str
    as_of: str
    revision: int = Field(ge=0)


@dataclass
class Aggregate:
    row_id: str
    parent_id: str | None
    level: HierarchyLevel
    label: str
    country_code: str | None
    population: int
    city_count: int
    fields: tuple[str, ...]
    weight_source: str = "GeoNames cities500 population"
    population_scale: float = 1
    counts_by_field: dict[str, dict[str, int]] = field(default_factory=dict)
    population_by_field: dict[str, dict[str, int]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for feature in self.fields:
            self.counts_by_field.setdefault(feature, defaultdict(int))
            self.population_by_field.setdefault(feature, defaultdict(int))

    def add(self, other: "Aggregate") -> None:
        self.population += other.population
        self.city_count += other.city_count
        for feature in self.fields:
            for status in ("present", "inherited", "imputed", "missing"):
                self.counts_by_field[feature][status] += other.counts_by_field[feature][status]
                self.population_by_field[feature][status] += other.population_by_field[feature][
                    status
                ]

    def to_row(self) -> HierarchyBrowserRow:
        counts = {
            status: sum(self.counts_by_field[feature][status] for feature in self.fields)
            for status in ("present", "inherited", "imputed", "missing")
        }
        missing_fields = sorted(
            (feature for feature in self.fields if self.counts_by_field[feature]["missing"] > 0),
            key=lambda feature: (
                -self.population_by_field[feature]["missing"],
                self.fields.index(feature),
            ),
        )
        population_denominator = self.population * len(self.fields)
        count_denominator = self.city_count * len(self.fields)

        def coverage(statuses: tuple[str, ...]) -> float:
            if population_denominator:
                numerator = sum(
                    self.population_by_field[feature][status]
                    for feature in self.fields
                    for status in statuses
                )
                return round(numerator * 100 / population_denominator, 6)
            if count_denominator:
                numerator = sum(counts[status] for status in statuses)
                return round(numerator * 100 / count_denominator, 6)
            return 0

        available = counts["present"] + counts["inherited"] + counts["imputed"]
        if available == 0:
            state: HierarchyCoverageState = "no_data"
        elif counts["missing"] > 0:
            state = "partial"
        elif counts["present"] + counts["inherited"] == 0:
            state = "imputed_only"
        else:
            state = "complete"
        return HierarchyBrowserRow(
            row_id=self.row_id,
            parent_id=self.parent_id,
            level=self.level,
            label=self.label,
            country_code=self.country_code,
            population=self.population,
            city_count=self.city_count,
            measured_coverage_percent=coverage(("present",)),
            effective_coverage_percent=coverage(("present", "inherited")),
            counts=HierarchyCoverageCounts(**counts),
            status=state,
            missing_fields=missing_fields,
            missing_field_count=len(missing_fields),
            missing_impact=round(
                sum(
                    max(0, self.population_by_field[feature]["missing"])
                    for feature in self.fields
                )
            ),
            weight_source=self.weight_source,
            has_children=True,
        )


def _country_aggregates(conn, fields: tuple[str, ...]) -> dict[str, Aggregate]:
    weights = {
        row["place"]: row["population"]
        for row in conn.execute(
            """SELECT p.place,p.population FROM registry_population_weights p
            WHERE p.level='country' AND p.rowid=(
                SELECT MAX(current.rowid) FROM registry_population_weights current
                WHERE current.level=p.level AND current.place=p.place
            )"""
        )
    }
    countries = {
        row["country_code"]: Aggregate(
            row_id=f"country:{row['country_code']}",
            parent_id=f"region:{country_region(row['country_code'])}",
            level="country",
            label=row["name"] or row["country_code"],
            country_code=row["country_code"],
            population=weights.get(row["country_code"], row["population"]),
            city_count=row["city_count"],
            fields=fields,
            weight_source=(
                "UN WPP 2024 Revision population"
                if row["country_code"] in weights
                else "GeoNames cities500 population"
            ),
            population_scale=(
                weights[row["country_code"]] / row["population"]
                if row["country_code"] in weights and row["population"]
                else 1
            ),
        )
        for row in conn.execute(
            """SELECT c.country_code,n.name,COUNT(*) city_count,
            COALESCE(SUM(c.population),0) population
            FROM cities c LEFT JOIN countries n ON n.code=c.country_code
            GROUP BY c.country_code,n.name"""
        )
    }
    for aggregate in countries.values():
        for feature in fields:
            aggregate.counts_by_field[feature]["missing"] = aggregate.city_count
            aggregate.population_by_field[feature]["missing"] = aggregate.population
    placeholders = ",".join("?" for _ in fields)
    for row in conn.execute(
        f"""SELECT c.country_code,r.field,r.field_status,COUNT(*) city_count,
        COALESCE(SUM(c.population),0) population
        FROM resolved r JOIN cities c USING(geonameid)
        WHERE r.field IN ({placeholders})
        GROUP BY c.country_code,r.field,r.field_status""",
        fields,
    ):
        aggregate = countries[row["country_code"]]
        feature = row["field"]
        status = row["field_status"]
        weighted_population = row["population"] * aggregate.population_scale
        aggregate.counts_by_field[feature][status] += row["city_count"]
        aggregate.population_by_field[feature][status] += weighted_population
        aggregate.counts_by_field[feature]["missing"] -= row["city_count"]
        aggregate.population_by_field[feature]["missing"] -= weighted_population
    return countries


def _region_aggregates(
    countries: dict[str, Aggregate], fields: tuple[str, ...]
) -> dict[str, Aggregate]:
    regions = {
        region: Aggregate(
            row_id=f"region:{region}",
            parent_id=None,
            level="region",
            label=region,
            country_code=None,
            population=0,
            city_count=0,
            fields=fields,
        )
        for region in CANONICAL_REGIONS
    }
    for country in countries.values():
        regions[country_region(country.country_code or "")].add(country)
    for region in regions.values():
        if region.population and all(
            country.weight_source == "UN WPP 2024 Revision population"
            for country in countries.values()
            if country_region(country.country_code or "") == region.label
        ):
            region.weight_source = "UN WPP 2024 Revision population"
        elif any(
            country.weight_source == "UN WPP 2024 Revision population"
            for country in countries.values()
            if country_region(country.country_code or "") == region.label
        ):
            region.weight_source = "UN WPP 2024 Revision with GeoNames fallback"
    return regions


def _row_sort_key(row: HierarchyBrowserRow) -> tuple[int, int, str, str]:
    return STATUS_ORDER[row.status], -row.population, row.label.casefold(), row.row_id


def _filtered_rows(
    rows: list[HierarchyBrowserRow], search: str, page: int, page_size: int
) -> tuple[list[HierarchyBrowserRow], int]:
    term = search.casefold().strip()
    filtered = [
        row
        for row in rows
        if not term or term in row.label.casefold() or term == (row.country_code or "").casefold()
    ]
    filtered.sort(key=_row_sort_key)
    start = (page - 1) * page_size
    return filtered[start : start + page_size], len(filtered)


def _city_rows(
    conn,
    country_code: str,
    search: str,
    page: int,
    page_size: int,
    fields: tuple[str, ...],
):
    clauses = ["country_code=?"]
    parameters: list[str | int] = [country_code]
    term = search.strip()
    if term:
        escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        clauses.append(
            "(name LIKE ? ESCAPE '\\' COLLATE NOCASE OR asciiname LIKE ? ESCAPE '\\' "
            "COLLATE NOCASE OR CAST(geonameid AS TEXT)=?)"
        )
        parameters.extend((f"%{escaped}%", f"%{escaped}%", term))
    where = " AND ".join(clauses)
    total = conn.execute(
        f"SELECT COUNT(*) FROM hierarchy_coverage WHERE {where}", parameters
    ).fetchone()[0]
    rows = conn.execute(
        f"""SELECT * FROM hierarchy_coverage WHERE {where} ORDER BY
        CASE WHEN available=0 THEN 0 WHEN available<? THEN 1
             WHEN direct+inherited=0 AND imputed>0 THEN 2 ELSE 3 END,
        population DESC,name COLLATE NOCASE,geonameid LIMIT ? OFFSET ?""",
        [*parameters, len(fields), page_size, (page - 1) * page_size],
    ).fetchall()
    return _materialize_city_rows(conn, rows, fields), total


def _materialize_city_rows(conn, rows, fields: tuple[str, ...]) -> list[HierarchyBrowserRow]:
    if not rows:
        return []
    identities = [row["geonameid"] for row in rows]
    placeholders = ",".join("?" for _ in identities)
    resolved = {
        (row["geonameid"], row["field"]): row["field_status"]
        for row in conn.execute(
            "SELECT geonameid,field,field_status FROM resolved "
            f"WHERE geonameid IN ({placeholders})",
            identities,
        )
    }
    result = []
    for source in rows:
        statuses = {
            feature: resolved.get((source["geonameid"], feature), "missing") for feature in fields
        }
        counts = {
            status: sum(value == status for value in statuses.values())
            for status in ("present", "inherited", "imputed", "missing")
        }
        missing_fields = [feature for feature in fields if statuses[feature] == "missing"]
        available = len(fields) - counts["missing"]
        if available == 0:
            state: HierarchyCoverageState = "no_data"
        elif counts["missing"]:
            state = "partial"
        elif counts["present"] + counts["inherited"] == 0:
            state = "imputed_only"
        else:
            state = "complete"
        result.append(
            HierarchyBrowserRow(
                row_id=f"city:{source['geonameid']}",
                parent_id=f"country:{source['country_code']}",
                level="city",
                label=source["name"],
                country_code=source["country_code"],
                geonameid=source["geonameid"],
                population=source["population"],
                city_count=1,
                measured_coverage_percent=round(counts["present"] * 100 / len(fields), 6),
                effective_coverage_percent=round(
                    (counts["present"] + counts["inherited"]) * 100 / len(fields), 6
                ),
                counts=HierarchyCoverageCounts(**counts),
                status=state,
                missing_fields=missing_fields,
                missing_field_count=len(missing_fields),
                missing_impact=source["population"] * counts["missing"],
                weight_source="GeoNames cities500 population",
                has_children=False,
            )
        )
    return result


def _queue(
    conn,
    regions: dict[str, Aggregate],
    countries: dict[str, Aggregate],
    limit: int,
    fields: tuple[str, ...],
) -> list[HierarchyBrowserRow]:
    aggregate_rows = [
        row
        for row in [
            *(aggregate.to_row() for aggregate in regions.values()),
            *(aggregate.to_row() for aggregate in countries.values()),
        ]
        if row.missing_impact > 0
    ]
    city_sources = conn.execute(
        """SELECT * FROM hierarchy_coverage WHERE available<? AND population>0
        ORDER BY population*(?-available) DESC,population DESC,geonameid LIMIT ?""",
        (len(fields), len(fields), limit),
    ).fetchall()
    candidates = [*aggregate_rows, *_materialize_city_rows(conn, city_sources, fields)]
    candidates.sort(
        key=lambda row: (
            -row.missing_impact,
            LEVEL_ORDER[row.level],
            row.label.casefold(),
            row.row_id,
        )
    )
    return candidates[:limit]


def _region_from_parent(parent_id: str | None) -> str:
    if not parent_id or not parent_id.startswith("region:"):
        raise ValueError("Country rows require a region parent")
    region = parent_id.removeprefix("region:")
    if region not in CANONICAL_REGIONS:
        raise ValueError("Unknown region")
    return region


def _country_from_parent(parent_id: str | None, countries: dict[str, Aggregate]) -> str:
    if not parent_id or not parent_id.startswith("country:"):
        raise ValueError("City rows require a country parent")
    country_code = parent_id.removeprefix("country:").upper()
    if country_code not in countries:
        raise ValueError("Unknown country")
    return country_code


def _create_hierarchy_coverage(conn, fields: tuple[str, ...]) -> None:
    placeholders = ",".join("?" for _ in fields)
    conn.execute(
        f"""CREATE TEMP TABLE hierarchy_coverage AS SELECT c.*,
        COUNT(r.field) available,
        COALESCE(SUM(r.field_status='present'),0) direct,
        COALESCE(SUM(r.field_status='inherited'),0) inherited,
        COALESCE(SUM(r.field_status='imputed'),0) imputed
        FROM cities c LEFT JOIN resolved r ON r.geonameid=c.geonameid
        AND r.field IN ({placeholders}) GROUP BY c.geonameid""",
        fields,
    )
    conn.execute("CREATE INDEX hierarchy_coverage_country ON hierarchy_coverage(country_code)")


def hierarchy_browser_page(
    store: AtlasStore,
    scope: str = "shared",
    as_of: str | None = None,
    level: HierarchyLevel = "region",
    parent_id: str | None = None,
    search: str = "",
    page: int = 1,
    page_size: int = 50,
    queue_limit: int = 20,
    fields: tuple[str, ...] | None = None,
) -> HierarchyBrowserPage:
    if page < 1:
        raise ValueError("Page must be at least one")
    if not 1 <= page_size <= 100:
        raise ValueError("Page size must be between one and 100")
    if not 1 <= queue_limit <= 100:
        raise ValueError("Queue limit must be between one and 100")
    selected_fields = tuple(FIELDS if fields is None else fields)
    if not selected_fields or len(selected_fields) != len(set(selected_fields)):
        raise ValueError("Hierarchy fields must be non-empty and unique")
    selected_date = as_of or date.today().isoformat()
    with store.connection() as conn:
        conn.execute("BEGIN")
        resolve(conn, scope, selected_date, selected_fields)
        _create_hierarchy_coverage(conn, selected_fields)
        countries = _country_aggregates(conn, selected_fields)
        regions = _region_aggregates(countries, selected_fields)
        if level == "region":
            if parent_id:
                raise ValueError("Region rows do not accept a parent")
            rows, filtered_count = _filtered_rows(
                [aggregate.to_row() for aggregate in regions.values()],
                search,
                page,
                page_size,
            )
            breadcrumbs = [HierarchyBreadcrumb(label="Regions", level="region")]
        elif level == "country":
            region = _region_from_parent(parent_id)
            rows, filtered_count = _filtered_rows(
                [
                    aggregate.to_row()
                    for aggregate in countries.values()
                    if country_region(aggregate.country_code or "") == region
                ],
                search,
                page,
                page_size,
            )
            breadcrumbs = [
                HierarchyBreadcrumb(label="Regions", level="region"),
                HierarchyBreadcrumb(label=region, level="country", parent_id=parent_id),
            ]
        elif level == "city":
            country_code = _country_from_parent(parent_id, countries)
            country = countries[country_code]
            region = country_region(country_code)
            rows, filtered_count = _city_rows(
                conn, country_code, search, page, page_size, selected_fields
            )
            breadcrumbs = [
                HierarchyBreadcrumb(label="Regions", level="region"),
                HierarchyBreadcrumb(
                    label=region,
                    level="country",
                    parent_id=f"region:{region}",
                ),
                HierarchyBreadcrumb(
                    label=country.label,
                    level="city",
                    parent_id=parent_id,
                ),
            ]
        else:
            raise ValueError("Unknown hierarchy level")
        return HierarchyBrowserPage(
            level=level,
            parent_id=parent_id,
            rows=rows,
            queue=_queue(conn, regions, countries, queue_limit, selected_fields),
            breadcrumbs=breadcrumbs,
            filtered_count=filtered_count,
            page=page,
            page_size=page_size,
            scope=scope,
            as_of=selected_date,
            revision=AtlasStore.revision(conn),
        )
