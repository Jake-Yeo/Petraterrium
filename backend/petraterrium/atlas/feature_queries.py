import hashlib
import json
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import Field

from ..contracts import Contract
from .database import AtlasStore
from .feature_catalog import FeatureCatalogStore
from .features import canonical_feature_registry
from .joint_estimates import (
    FeatureFilter,
    FeatureInheritanceView,
    JoinedFilterEstimate,
    MeasuredJointData,
    PlaceSelector,
    PopulationPlace,
    estimate_joined_filters,
    feature_inheritance,
)
from .regions import CANONICAL_REGIONS, country_region


class PlaceOptions(Contract):
    places: list[PlaceSelector]


class FeatureInheritanceRequest(Contract):
    selector: PlaceSelector
    feature_id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")


class JoinedFilterRequest(Contract):
    selector: PlaceSelector
    filters: list[FeatureFilter] = Field(min_length=2)


QUERY_SCHEMA = """
CREATE TABLE IF NOT EXISTS feature_joint_data(
 record_id TEXT PRIMARY KEY, level TEXT NOT NULL, place TEXT NOT NULL,
 conditions_key TEXT NOT NULL, record_json TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS feature_joint_data_lookup
ON feature_joint_data(level,place,conditions_key);
CREATE TABLE IF NOT EXISTS missing_joint_requests(
 request_id TEXT PRIMARY KEY, selector_json TEXT NOT NULL, filters_json TEXT NOT NULL,
 requirement TEXT NOT NULL, first_requested_at TEXT NOT NULL, last_requested_at TEXT NOT NULL,
 request_count INTEGER NOT NULL
);
"""


class FeatureQueryService:
    def __init__(self, store: AtlasStore):
        self.store = store
        self.catalog = FeatureCatalogStore(store)
        with store.connection() as connection:
            connection.executescript(QUERY_SCHEMA)

    def registry(self):
        return self.catalog.enriched_registry(canonical_feature_registry())

    def place_options(self, search: str = "", limit: int = 25) -> PlaceOptions:
        with self.store.connection() as connection:
            countries = connection.execute(
                """SELECT c.country_code,COALESCE(n.name,c.country_code) label,
                SUM(c.population) population FROM cities c
                LEFT JOIN countries n ON n.code=c.country_code
                WHERE c.population>0 GROUP BY c.country_code,n.name
                ORDER BY label"""
            ).fetchall()
            places = [PlaceSelector(level="global", place="global", label="Global")]
            places.extend(
                PlaceSelector(level="region", place=region, label=region)
                for region in CANONICAL_REGIONS
                if any(country_region(row["country_code"]) == region for row in countries)
            )
            places.extend(
                PlaceSelector(
                    level="country",
                    place=row["country_code"],
                    label=row["label"],
                )
                for row in countries
            )
            term = search.strip()
            if term:
                escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                rows = connection.execute(
                    """SELECT geonameid,name,country_code FROM cities
                    WHERE name LIKE ? ESCAPE '\\' COLLATE NOCASE
                    OR asciiname LIKE ? ESCAPE '\\' COLLATE NOCASE
                    OR CAST(geonameid AS TEXT)=?
                    ORDER BY population DESC,name COLLATE NOCASE LIMIT ?""",
                    (f"%{escaped}%", f"%{escaped}%", term, limit),
                ).fetchall()
                places.extend(
                    PlaceSelector(
                        level="city",
                        place=str(row["geonameid"]),
                        label=f"{row['name']}, {row['country_code']}",
                    )
                    for row in rows
                )
        return PlaceOptions(places=places)

    def population_places(self, selector: PlaceSelector) -> list[PopulationPlace]:
        if selector.level == "city":
            return self._city_population_place(selector.place)
        if selector.level not in {"global", "region", "country"}:
            raise ValueError("Subregion population weights are not loaded")
        return self._country_population_places(selector)

    def _city_population_place(self, place: str) -> list[PopulationPlace]:
        with self.store.connection() as connection:
            rows = connection.execute(
                """SELECT geonameid,name,country_code,population FROM cities
                WHERE population>0 AND CAST(geonameid AS TEXT)=?""",
                (place,),
            ).fetchall()
        return [
            PopulationPlace(
                place=str(row["geonameid"]),
                label=f"{row['name']}, {row['country_code']}",
                level="city",
                population=row["population"],
                city=str(row["geonameid"]),
                country=row["country_code"],
                region=country_region(row["country_code"]),
            )
            for row in rows
        ]

    def _country_population_places(self, selector: PlaceSelector) -> list[PopulationPlace]:
        with self.store.connection() as connection:
            city_rows = connection.execute(
                """SELECT c.country_code,COALESCE(n.name,c.country_code) label,
                SUM(c.population) population FROM cities c
                LEFT JOIN countries n ON n.code=c.country_code
                WHERE c.population>0 GROUP BY c.country_code,n.name"""
            ).fetchall()
            weight_rows = connection.execute(
                """SELECT p.place,p.population FROM registry_population_weights p
                WHERE p.level='country' AND p.rowid=(
                    SELECT MAX(current.rowid) FROM registry_population_weights current
                    WHERE current.level=p.level AND current.place=p.place
                )"""
            ).fetchall()
        weights = {row["place"]: row["population"] for row in weight_rows}
        places = []
        for row in city_rows:
            code = row["country_code"]
            region = country_region(code)
            if selector.level == "country" and code != selector.place.upper():
                continue
            if selector.level == "region" and region != selector.place:
                continue
            population = weights.get(code, row["population"])
            if population <= 0:
                continue
            places.append(
                PopulationPlace(
                    place=code,
                    label=row["label"],
                    level="country",
                    population=population,
                    country=code,
                    region=region,
                )
            )
        return places

    def _region_codes(self, region: str) -> list[str]:
        if region not in CANONICAL_REGIONS:
            raise ValueError("Unknown region")
        with self.store.connection() as connection:
            rows = connection.execute("SELECT DISTINCT country_code FROM cities")
            codes = [row[0] for row in rows]
        return [code for code in codes if country_region(code) == region]

    def measured_joints(self) -> list[MeasuredJointData]:
        with self.store.connection() as connection:
            rows = connection.execute(
                "SELECT record_json FROM feature_joint_data ORDER BY created_at DESC"
            ).fetchall()
        return [MeasuredJointData.model_validate_json(row["record_json"]) for row in rows]

    def record_missing(self, estimate: JoinedFilterEstimate) -> None:
        if not estimate.missing_requirement:
            return
        payload = {
            "selector": estimate.selector.model_dump(mode="json"),
            "filters": [item.model_dump(mode="json") for item in estimate.filters],
        }
        request_id = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        now = datetime.now(UTC).isoformat()
        with self.store.connection() as connection:
            connection.execute(
                """INSERT INTO missing_joint_requests VALUES(?,?,?,?,?,?,1)
                ON CONFLICT(request_id) DO UPDATE SET
                last_requested_at=excluded.last_requested_at,
                request_count=missing_joint_requests.request_count+1""",
                (
                    request_id,
                    estimate.selector.model_dump_json(),
                    json.dumps([item.model_dump(mode="json") for item in estimate.filters]),
                    estimate.missing_requirement,
                    now,
                    now,
                ),
            )


def create_feature_query_router(store: AtlasStore) -> APIRouter:
    service = FeatureQueryService(store)
    router = APIRouter(prefix="/atlas/feature-query", tags=["Feature queries"])

    def checked(function, *args):
        try:
            return function(*args)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error

    @router.get("/places", response_model=PlaceOptions)
    def places(search: str = Query("", max_length=120), limit: int = Query(25, ge=1, le=50)):
        return service.place_options(search, limit)

    @router.post("/inheritance", response_model=FeatureInheritanceView)
    def inheritance(request: FeatureInheritanceRequest):
        return checked(
            feature_inheritance,
            service.registry(),
            service.population_places(request.selector),
            request.selector,
            request.feature_id,
        )

    @router.post("/joined", response_model=JoinedFilterEstimate)
    def joined(request: JoinedFilterRequest):
        estimate = checked(
            estimate_joined_filters,
            service.registry(),
            service.population_places(request.selector),
            request.selector,
            request.filters,
            service.measured_joints(),
        )
        service.record_missing(estimate)
        return estimate

    return router
