import hashlib
import json

from .contracts import Country

# FAKE populations. TODO(real-atlas): replace invented counts with a dated population atlas.
COUNTRIES = (
    Country(country="ITA", name="Italy", population=1_000_000, latitude=42.8, longitude=12.8),
    Country(country="FRA", name="France", population=900_000, latitude=46.6, longitude=2.2),
    Country(country="DEU", name="Germany", population=1_200_000, latitude=51.2, longitude=10.4),
    Country(country="ESP", name="Spain", population=800_000, latitude=40.4, longitude=-3.7),
)
COUNTRY_BY_CODE = {country.country: country for country in COUNTRIES}
DATA_VERSION = (
    "FAKE-atlas-v1+"
    + hashlib.sha256(
        json.dumps([c.model_dump() for c in COUNTRIES], sort_keys=True).encode()
    ).hexdigest()[:12]
)
