import hashlib
from pathlib import Path

import httpx

from ..backbone import GEONAMES_URL
from .households import HOUSEHOLD_URL
from .ucdb import UCDB_URL
from .wdi import WDI_URL

SOURCE_FILES = {
    "cities500.zip": GEONAMES_URL,
    "GHS_UCDB_GLOBE_R2024A_V1_2.zip": UCDB_URL,
    "WDI_CSV.zip": WDI_URL,
    "UN_DESA_household_2026.xlsx": HOUSEHOLD_URL,
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, destination: Path, refresh=False) -> Path:
    if destination.exists() and not refresh:
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    headers = {"User-Agent": "Petraterrium data atlas/1.0"}
    with httpx.stream(
        "GET", url, headers=headers, follow_redirects=True, timeout=300
    ) as response:
        response.raise_for_status()
        with temporary.open("wb") as target:
            for chunk in response.iter_bytes():
                target.write(chunk)
    temporary.replace(destination)
    return destination


def acquire_sources(data_directory: Path, refresh=False):
    source_directory = data_directory / "sources"
    paths = {}
    for filename, url in SOURCE_FILES.items():
        destination = (
            data_directory / filename
            if filename == "cities500.zip"
            else source_directory / filename
        )
        paths[filename] = download(url, destination, refresh)
    return paths
