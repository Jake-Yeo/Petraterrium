import runpy
from pathlib import Path


def test_frontend_types_and_schema_match_backend_contracts():
    exporter = Path(__file__).resolve().parents[1] / "scripts" / "export_contracts.py"
    namespace = runpy.run_path(str(exporter))
    for path, expected in namespace["artifacts"]().items():
        assert path.read_text() == expected, f"Regenerate frontend contracts: {path.name}"
