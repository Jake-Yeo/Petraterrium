import json
from datetime import date

from .contracts import (
    AtlasCity,
    AtlasCountry,
    AtlasOverview,
    AtlasSummary,
    Backbone,
    BehaviourModel,
    CityDetail,
    CoverageCounts,
    DataGap,
    FieldCoverage,
    LegacyMarginalField,
    MarginalField,
    Provenance,
)
from .database import FIELDS, LEGACY_FIELDS, SUGGESTIONS, AtlasStore
from .regions import country_region


def provenance(row) -> Provenance:
    return Provenance(**{key: row[key] for key in Provenance.model_fields})


def research_trace(row) -> dict:
    return {
        "attempt_id": row["attempt_id"],
        "result_kind": row["result_kind"],
        "mapping": json.loads(row["mapping_json"]),
        "mapping_confirmed": bool(row["mapping_confirmed"]),
        "verification": json.loads(row["verification_json"]),
        "sources": json.loads(row["sources_json"]),
        "search_log": json.loads(row["search_log_json"]),
        "estimate_trace": json.loads(row["estimate_trace_json"])
        if row["estimate_trace_json"]
        else None,
        "languages": json.loads(row["languages_json"]),
        "better_data": row["better_data"],
    }


def resolve(
    conn,
    scope: str,
    as_of: str,
    fields: tuple[str, ...] = FIELDS,
) -> None:
    conn.execute("CREATE TEMP TABLE country_regions(code TEXT PRIMARY KEY,region TEXT NOT NULL)")
    conn.executemany(
        "INSERT INTO country_regions VALUES(?,?)",
        [
            (row["country_code"], country_region(row["country_code"]))
            for row in conn.execute("SELECT DISTINCT country_code FROM cities")
        ],
    )
    conn.execute(
        """CREATE TEMP TABLE resolved_all AS
        WITH observations_scoped AS MATERIALIZED (
            SELECT o.id,o.geo_level,o.geo_key,o.field,o.evidence_status,v.scope
            FROM observations o JOIN imports v USING(import_id)
            WHERE v.status='committed' AND v.scope IN ('shared',:scope)
            AND v.source_date<=:as_of AND v.published_date<=:as_of
        ), observations_current AS MATERIALIZED (
            SELECT id,geo_level,geo_key,field,evidence_status,scope FROM (
                SELECT *,ROW_NUMBER() OVER(PARTITION BY geo_level,geo_key,field
                ORDER BY (scope=:scope) DESC,(evidence_status='measured') DESC,id DESC) geo_position
                FROM observations_scoped
            ) WHERE geo_position=1
        ), candidates AS (
            SELECT c.geonameid,o.id observation_id,o.field,o.scope,
            3 specificity,CASE WHEN o.evidence_status='estimated'
            THEN 'estimated' ELSE 'present' END field_status
            FROM observations_current o JOIN cities c ON c.geonameid=CAST(o.geo_key AS INTEGER)
            WHERE o.geo_level='city'
            UNION ALL
            SELECT c.geonameid,o.id observation_id,o.field,o.scope,
            2 specificity,CASE WHEN o.evidence_status='estimated'
            THEN 'estimated' ELSE 'imputed' END field_status
            FROM observations_current o JOIN cities c
            ON c.country_code||':'||c.admin1=o.geo_key WHERE o.geo_level='region'
            UNION ALL
            SELECT c.geonameid,o.id observation_id,o.field,o.scope,
            2 specificity,CASE WHEN o.evidence_status='estimated'
            THEN 'estimated' ELSE 'imputed' END field_status
            FROM observations_current o JOIN city_lau_matches m ON m.gisco_id=o.geo_key
            JOIN cities c ON c.geonameid=m.geonameid WHERE o.geo_level='lau'
            UNION ALL
            SELECT c.geonameid,o.id observation_id,o.field,o.scope,
            1 specificity,CASE WHEN o.evidence_status='estimated'
            THEN 'estimated' ELSE 'inherited' END field_status
            FROM observations_current o JOIN cities c ON c.country_code=o.geo_key
            WHERE o.geo_level='country'
            UNION ALL
            SELECT c.geonameid,o.id observation_id,o.field,o.scope,
            0 specificity,CASE WHEN o.evidence_status='estimated'
            THEN 'estimated' ELSE 'imputed' END field_status
            FROM observations_current o JOIN country_regions g ON g.region=o.geo_key
            JOIN cities c ON c.country_code=g.code WHERE o.geo_level='canonical_region'
        ), ranked AS (
            SELECT *,ROW_NUMBER() OVER(PARTITION BY geonameid,field
            ORDER BY specificity DESC,(scope=:scope) DESC,observation_id DESC) position
            FROM candidates
        ) SELECT geonameid,observation_id,field,field_status
        FROM ranked WHERE position=1""",
        {"scope": scope, "as_of": as_of},
    )
    active_fields = ",".join("?" for _ in fields)
    legacy_fields = ",".join("?" for _ in LEGACY_FIELDS)
    conn.execute(
        "CREATE TEMP TABLE resolved AS SELECT * FROM resolved_all "
        f"WHERE field IN ({active_fields})",
        fields,
    )
    conn.execute(
        "CREATE TEMP TABLE legacy_resolved AS SELECT * FROM resolved_all "
        f"WHERE field IN ({legacy_fields})",
        LEGACY_FIELDS,
    )
    conn.execute("CREATE UNIQUE INDEX resolved_city_field ON resolved(geonameid,field)")
    field_count = len(fields)
    conn.execute(f"""CREATE TEMP VIEW coverage AS SELECT c.*,
        COALESCE(r.direct,0) direct,COALESCE(r.inherited,0) inherited,
        COALESCE(r.imputed,0) imputed,COALESCE(r.estimated,0) estimated,
        COALESCE(r.available,0) available,
        CASE WHEN COALESCE(r.direct,0)={field_count} THEN 'full'
             WHEN COALESCE(r.direct,0)>0 THEN 'partial' ELSE 'none' END coverage_state,
        CASE WHEN COALESCE(r.available,0)<{field_count} THEN 'missing'
             WHEN r.estimated>0 THEN 'estimated'
             WHEN r.imputed>0 THEN 'imputed'
             WHEN r.inherited>0 THEN 'inherited' ELSE 'present' END status
        FROM cities c LEFT JOIN (SELECT geonameid,COUNT(*) available,
        SUM(field_status='present') direct,SUM(field_status='inherited') inherited,
        SUM(field_status='imputed') imputed,
        SUM(field_status='estimated') estimated FROM resolved
        GROUP BY geonameid) r USING(geonameid)""")


def models_for(
    conn, countries: list[str], scope: str, as_of: str
) -> dict[str, list[BehaviourModel]]:
    if not countries:
        return {}
    placeholders = ",".join("?" for _ in countries)
    rows = conn.execute(
        f"""SELECT m.*,v.* FROM models m JOIN imports v USING(import_id)
        WHERE v.status='committed' AND v.scope IN ('shared',?) AND v.source_date<=?
        AND v.published_date<=? AND m.active=1 AND m.country_code IN ({placeholders})
        ORDER BY (v.scope=?) DESC,m.id DESC""",
        [scope, as_of, as_of, *countries, scope],
    ).fetchall()
    result = {}
    seen = set()
    for row in rows:
        key = (row["country_code"], row["behaviour"])
        if key in seen:
            continue
        seen.add(key)
        result.setdefault(row["country_code"], []).append(
            BehaviourModel(
                country_code=row["country_code"],
                behaviour=row["behaviour"],
                fitted=bool(row["fitted"]),
                label_only=bool(row["label_only"]),
                provenance=provenance(row),
                heldout_loss=row["heldout_loss"],
                baseline_loss=row["baseline_loss"],
                training_rows=row["training_rows"],
                heldout_rows=row["heldout_rows"],
                traits=json.loads(row["traits_json"]),
            )
        )
    return result


def city_results(conn, rows, scope: str, as_of: str) -> list[AtlasCity]:
    if not rows:
        return []
    identities = [row["geonameid"] for row in rows]
    placeholders = ",".join("?" for _ in identities)
    resolved = {
        (row["geonameid"], row["field"]): row
        for row in conn.execute(
            f"""SELECT r.*,o.value_json,o.unit,v.* FROM resolved r
            JOIN observations o ON o.id=r.observation_id
            JOIN imports v USING(import_id)
            WHERE r.geonameid IN ({placeholders})""",
            identities,
        )
    }
    import_ids = sorted(
        {row["import_id"] for row in resolved.values() if row["import_id"]}
    )
    traces = {}
    if import_ids:
        import_placeholders = ",".join("?" for _ in import_ids)
        traces = {
            row["promoted_import_id"]: research_trace(row)
            for row in conn.execute(
                "SELECT * FROM auto_import_attempts "
                f"WHERE promoted_import_id IN ({import_placeholders})",
                import_ids,
            )
        }
    countries = {row["code"]: row["name"] for row in conn.execute("SELECT * FROM countries")}
    behaviours = models_for(conn, list({row["country_code"] for row in rows}), scope, as_of)
    densities = {}
    for row in conn.execute(
        f"""SELECT d.*,v.* FROM densities d JOIN imports v USING(import_id)
        WHERE d.geonameid IN ({placeholders}) AND v.scope IN ('shared',?)
        AND v.status='committed' AND v.source_date<=? AND v.published_date<=?
        ORDER BY (v.scope=?) DESC,d.id DESC""",
        [*identities, scope, as_of, as_of, scope],
    ):
        densities.setdefault(row["geonameid"], row)
    results = []
    for row in rows:
        fields = []
        for field in FIELDS:
            observation = resolved.get((row["geonameid"], field))
            fields.append(
                MarginalField(
                    field=field,
                    status=observation["field_status"] if observation else "missing",
                    value=json.loads(observation["value_json"]) if observation else None,
                    unit=observation["unit"] if observation else None,
                    provenance=provenance(observation) if observation else None,
                    research_trace=traces.get(observation["import_id"])
                    if observation
                    else None,
                    suggested_source=SUGGESTIONS[field][0],
                    source_url=SUGGESTIONS[field][1],
                )
            )
        density = densities.get(row["geonameid"])
        results.append(
            AtlasCity(
                **{
                    key: row[key]
                    for key in (
                        "geonameid",
                        "name",
                        "asciiname",
                        "country_code",
                        "admin1",
                        "admin2",
                        "latitude",
                        "longitude",
                        "population",
                        "timezone",
                        "simulation_tier",
                    )
                },
                country_name=countries.get(row["country_code"], row["country_code"]),
                population_status="present" if row["population"] > 0 else "missing",
                tier_reason="Top metro tier; execution awaits a real-data engine"
                if row["simulation_tier"] == "simulated"
                else "Country population-share tier; density adjustment requires a population grid",
                coverage_percent=row["direct"] * 100 / len(FIELDS),
                inherited_coverage_percent=(row["direct"] + row["inherited"])
                * 100
                / len(FIELDS),
                resolved_coverage_percent=row["available"] * 100 / len(FIELDS),
                status=row["status"],
                coverage_state=row["coverage_state"],
                fields=fields,
                behaviour=behaviours.get(row["country_code"], []),
                density_per_km2=density["density"] if density else None,
                density_provenance=provenance(density) if density else None,
            )
        )
    return results


def summary(conn, scope: str, as_of: str) -> AtlasSummary:
    field_count = len(FIELDS)
    row = conn.execute(f"""SELECT COUNT(*) total,COALESCE(SUM(population),0) population,
        COALESCE(SUM(population<=0),0) unknown_population,
        COALESCE(SUM(direct={field_count}),0) full_count,
        COALESCE(SUM(direct>0 AND direct<{field_count}),0) partial,
        COALESCE(SUM(direct=0),0) none,
        COALESCE(SUM(direct+inherited={field_count}),0) effective_full,
        COALESCE(SUM(direct+inherited>0 AND direct+inherited<{field_count}),0) effective_partial,
        COALESCE(SUM(direct+inherited=0),0) effective_none,
        COALESCE(SUM(simulation_tier='simulated'),0) simulated FROM coverage""").fetchone()
    field_rows = {
        r["field"]: r
        for r in conn.execute("""SELECT r.field,
        SUM(field_status='present') present,SUM(field_status='inherited') inherited,
        SUM(field_status='imputed') imputed,SUM(field_status='estimated') estimated,
        SUM(CASE WHEN field_status='present' THEN c.population ELSE 0 END) direct_population,
        SUM(CASE WHEN field_status IN ('present','inherited')
            THEN c.population ELSE 0 END) inherited_population,
        SUM(CASE WHEN field_status='imputed' THEN c.population ELSE 0 END) imputed_population,
        SUM(CASE WHEN field_status='estimated' THEN c.population ELSE 0 END)
        estimated_population
        FROM resolved r JOIN cities c USING(geonameid) GROUP BY field""")
    }
    fields = []
    for field in FIELDS:
        values = dict(field_rows.get(field) or {})
        direct, inherited, imputed, estimated = (
            values.get(key, 0)
            for key in ("present", "inherited", "imputed", "estimated")
        )

        def percent(numerator, denominator):
            return round(numerator * 100 / denominator, 6) if denominator else 0

        fields.append(
            FieldCoverage(
                field=field,
                present=direct,
                inherited=inherited,
                imputed=imputed,
                estimated=estimated,
                missing=row["total"] - direct - inherited - imputed - estimated,
                direct_percent=percent(direct, row["total"]),
                direct_plus_inherited_percent=percent(direct + inherited, row["total"]),
                direct_population_percent=percent(
                    values.get("direct_population", 0), row["population"]
                ),
                direct_plus_inherited_population_percent=percent(
                    values.get("inherited_population", 0), row["population"]
                ),
                imputed_population_percent=percent(
                    values.get("imputed_population", 0), row["population"]
                ),
                estimated_population_percent=percent(
                    values.get("estimated_population", 0), row["population"]
                ),
            )
        )
    model_countries = conn.execute(
        """SELECT COUNT(DISTINCT m.country_code) FROM models m
        JOIN imports v USING(import_id) WHERE m.fitted=1 AND m.active=1 AND v.status='committed'
        AND v.scope IN ('shared',?) AND v.source_date<=? AND v.published_date<=?""",
        (scope, as_of, as_of),
    ).fetchone()[0]
    return AtlasSummary(
        total_cities=row["total"],
        total_population=row["population"],
        cities_without_population=row["unknown_population"],
        direct=CoverageCounts(full=row["full_count"], partial=row["partial"], none=row["none"]),
        direct_plus_inherited=CoverageCounts(
            full=row["effective_full"], partial=row["effective_partial"], none=row["effective_none"]
        ),
        fields=fields,
        simulated_cities=row["simulated"],
        disaggregated_cities=row["total"] - row["simulated"],
        countries_with_fitted_behaviour=model_countries,
        revision=AtlasStore.revision(conn),
        scope=scope,
        as_of=as_of,
    )


def overview(
    store: AtlasStore,
    scope="shared",
    as_of: str | None = None,
    search="",
    country="",
    tier="",
    status="",
    missing_field="",
    page=1,
    page_size=25,
) -> AtlasOverview:
    as_of = as_of or date.today().isoformat()
    with store.connection() as conn:
        conn.execute("BEGIN")
        resolve(conn, scope, as_of)
        clauses, parameters = [], []
        if search:
            clauses.append(
                "(name LIKE ? ESCAPE '\\' COLLATE NOCASE OR asciiname LIKE ? ESCAPE '\\'"
                " COLLATE NOCASE OR CAST(geonameid AS TEXT)=?)"
            )
            escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            parameters.extend([f"%{escaped}%", f"%{escaped}%", search])
        for column, value in (
            ("country_code", country),
            ("simulation_tier", tier),
            ("status", status),
        ):
            if value:
                clauses.append(f"{column}=?")
                parameters.append(value)
        if missing_field:
            clauses.append(
                "NOT EXISTS(SELECT 1 FROM resolved r WHERE"
                " r.geonameid=coverage.geonameid AND r.field=?)"
            )
            parameters.append(missing_field)
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        count = conn.execute(f"SELECT COUNT(*) FROM coverage {where}", parameters).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM coverage {where} ORDER BY population DESC,geonameid LIMIT ? OFFSET ?",
            [*parameters, page_size, (page - 1) * page_size],
        ).fetchall()
        fields_sql = " UNION ALL ".join("SELECT ? field" for _ in FIELDS)
        gaps = [
            DataGap(
                geonameid=r["geonameid"],
                city=r["name"],
                country_code=r["country_code"],
                population=r["population"],
                field=r["field"],
                status=r["field_status"] or "missing",
                suggested_source=SUGGESTIONS[r["field"]][0],
            )
            for r in conn.execute(
                f"""
            SELECT c.geonameid,c.name,c.country_code,c.population,f.field,r.field_status
            FROM cities c CROSS JOIN ({fields_sql}) f LEFT JOIN resolved r
            ON r.geonameid=c.geonameid AND r.field=f.field
            WHERE r.field_status IS NULL OR r.field_status!='present'
            ORDER BY c.population DESC,c.geonameid,f.field LIMIT 20""",
                FIELDS,
            )
        ]
        countries = [
            AtlasCountry(country_code=r["country_code"], name=r["country_name"], cities=r["n"])
            for r in conn.execute("""SELECT c.country_code,
                COALESCE(n.name,c.country_code) country_name,COUNT(*) n
                FROM cities c LEFT JOIN countries n ON n.code=c.country_code
                GROUP BY c.country_code ORDER BY country_name""")
        ]
        return AtlasOverview(
            summary=summary(conn, scope, as_of),
            cities=city_results(conn, rows, scope, as_of),
            filtered_count=count,
            page=page,
            page_size=page_size,
            countries=countries,
            gaps=gaps,
            backbone=Backbone(**store.metadata(conn, "backbone", {})),
        )


def city_detail(
    store: AtlasStore, identity: int, scope="shared", as_of: str | None = None
) -> CityDetail:
    as_of = as_of or date.today().isoformat()
    with store.connection() as conn:
        conn.execute("BEGIN")
        resolve(conn, scope, as_of)
        row = conn.execute("SELECT * FROM coverage WHERE geonameid=?", (identity,)).fetchone()
        if row is None:
            raise KeyError("City not found")
        city = city_results(conn, [row], scope, as_of)[0]
        legacy_rows = conn.execute(
            """SELECT r.*,o.value_json,o.unit,v.* FROM legacy_resolved r
            JOIN observations o ON o.id=r.observation_id
            JOIN imports v USING(import_id) WHERE r.geonameid=?""",
            (identity,),
        ).fetchall()
        history = conn.execute(
            """SELECT DISTINCT v.* FROM observations o JOIN imports v USING(import_id)
            WHERE v.status='committed' AND v.scope IN ('shared',?)
            AND v.source_date<=? AND v.published_date<=?
            AND ((o.geo_level='city' AND o.geo_key=?) OR (o.geo_level='country' AND o.geo_key=?)
            OR (o.geo_level='region' AND o.geo_key=?) OR (o.geo_level='lau' AND EXISTS(
            SELECT 1 FROM city_lau_matches m WHERE m.geonameid=? AND m.gisco_id=o.geo_key))
            OR (o.geo_level='canonical_region' AND o.geo_key=?))
            ORDER BY v.created_at DESC""",
            (
                scope,
                as_of,
                as_of,
                str(identity),
                city.country_code,
                city.country_code + ":" + city.admin1,
                identity,
                country_region(city.country_code),
            ),
        )
        return CityDetail(
            city=city,
            missing_fields=[f.field for f in city.fields if f.status == "missing"],
            direct_observation_gaps=[f.field for f in city.fields if f.status != "present"],
            history=[provenance(v) for v in history],
            legacy_fields=[
                LegacyMarginalField(
                    value=json.loads(item["value_json"]),
                    unit=item["unit"],
                    provenance=provenance(item),
                )
                for item in legacy_rows
            ],
            revision=store.revision(conn),
            simulation_note=(
                "Tier assignments organize the future country/top-metro engine. The"
                " current simulator remains FAKE and country-only; no city simulation"
                " values are invented."
            ),
        )
