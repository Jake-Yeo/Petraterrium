from collections import defaultdict
from datetime import date

from .contracts import HierarchyOverview, HierarchyRow
from .database import FIELDS, AtlasStore
from .organizer import resolve
from .regions import CANONICAL_REGIONS, country_region


def field_status(values: dict[str, int]) -> str:
    if values.get("inherited", 0):
        return "present"
    if values.get("present", 0) or values.get("imputed", 0):
        return "imputed"
    return "missing"


def hierarchy_overview(
    store: AtlasStore,
    scope: str = "shared",
    as_of: str | None = None,
) -> HierarchyOverview:
    selected_date = as_of or date.today().isoformat()
    with store.connection() as conn:
        conn.execute("BEGIN")
        resolve(conn, scope, selected_date)
        countries = conn.execute(
            """SELECT c.country_code,countries.name,COUNT(*) city_count,
            COALESCE(SUM(c.population),0) population
            FROM cities c LEFT JOIN countries ON countries.code=c.country_code
            GROUP BY c.country_code,countries.name ORDER BY c.country_code"""
        ).fetchall()
        coverage = conn.execute(
            """SELECT c.country_code,r.field,r.field_status,COUNT(*) city_count,
            COALESCE(SUM(c.population),0) population
            FROM resolved r JOIN cities c USING(geonameid)
            GROUP BY c.country_code,r.field,r.field_status"""
        ).fetchall()
    by_country = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    covered_population = defaultdict(lambda: defaultdict(int))
    for row in coverage:
        by_country[row["country_code"]][row["field"]][row["field_status"]] += row[
            "city_count"
        ]
        covered_population[row["country_code"]][row["field"]] += row["population"]
    country_rows = []
    region_countries = defaultdict(list)
    for row in countries:
        code = row["country_code"]
        region = country_region(code)
        region_countries[region].append(code)
        population = row["population"]
        statuses = {
            feature: field_status(by_country[code][feature]) for feature in FIELDS
        }
        percentages = {
            feature: round(covered_population[code][feature] * 100 / population, 6)
            if population
            else 0
            for feature in FIELDS
        }
        country_rows.append(
            HierarchyRow(
                row_id=f"country:{code}",
                level="country",
                parent_id=f"region:{region}",
                label=row["name"] or code,
                country_code=code,
                population=population,
                city_count=row["city_count"],
                statuses=statuses,
                coverage_by_field=percentages,
                weight_source="GeoNames cities500 population",
                children_paged=True,
            )
        )
    region_rows = []
    for region in CANONICAL_REGIONS:
        members = [row for row in country_rows if row.country_code in region_countries[region]]
        population = sum(row.population for row in members)
        statuses = {}
        percentages = {}
        for feature in FIELDS:
            covered = sum(
                row.population * row.coverage_by_field[feature] / 100 for row in members
            )
            percentages[feature] = round(covered * 100 / population, 6) if population else 0
            statuses[feature] = "imputed" if covered else "missing"
        region_rows.append(
            HierarchyRow(
                row_id=f"region:{region}",
                level="region",
                parent_id="global:world",
                label=region,
                population=population,
                city_count=sum(row.city_count for row in members),
                statuses=statuses,
                coverage_by_field=percentages,
                weight_source="GeoNames cities500 population",
            )
        )
    total_population = sum(row.population for row in region_rows)
    global_statuses = {}
    global_coverage = {}
    for feature in FIELDS:
        covered = sum(
            row.population * row.coverage_by_field[feature] / 100 for row in region_rows
        )
        global_coverage[feature] = (
            round(covered * 100 / total_population, 6) if total_population else 0
        )
        global_statuses[feature] = "imputed" if covered else "missing"
    global_row = HierarchyRow(
        row_id="global:world",
        level="global",
        label="Global",
        population=total_population,
        city_count=sum(row.city_count for row in region_rows),
        statuses=global_statuses,
        coverage_by_field=global_coverage,
        weight_source="GeoNames cities500 population",
    )
    return HierarchyOverview(
        rows=[global_row, *region_rows, *country_rows],
        scope=scope,
        as_of=selected_date,
        resolution_order=["city", "country", "subregion", "region", "global", "unknown"],
        mapping_version="canonical-regions-v1",
    )
