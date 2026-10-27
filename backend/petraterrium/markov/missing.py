import re
from pathlib import Path

from .models import MissingEvidenceRequirement

SECTION_START = "## Generated Markov evidence requirements"
SECTION_END = "## End generated Markov evidence requirements"
ENTRY_PATTERN = re.compile(r"^- \[ \] `([^`]+)`: (.+)$")


def existing_requirements(text: str) -> dict[str, str]:
    if SECTION_START not in text or SECTION_END not in text:
        return {}
    section = text.split(SECTION_START, 1)[1].split(SECTION_END, 1)[0]
    result: dict[str, str] = {}
    for line in section.splitlines():
        match = ENTRY_PATTERN.match(line)
        if match:
            result[match.group(1)] = match.group(2)
    return result


def rendered_section(entries: dict[str, str]) -> str:
    rows = [SECTION_START, ""]
    rows.extend(f"- [ ] `{key}`: {entries[key]}" for key in sorted(entries))
    rows.extend(["", SECTION_END])
    return "\n".join(rows)


def update_missing_requirements(
    path: Path,
    requirements: list[MissingEvidenceRequirement],
) -> None:
    text = path.read_text() if path.exists() else "# Missing evidence\n"
    entries = existing_requirements(text)
    entries.update({item.key: item.requirement for item in requirements})
    section = rendered_section(entries)
    if SECTION_START in text and SECTION_END in text:
        prefix, remainder = text.split(SECTION_START, 1)
        _, suffix = remainder.split(SECTION_END, 1)
        updated = f"{prefix.rstrip()}\n\n{section}{suffix}"
    else:
        updated = f"{text.rstrip()}\n\n{section}\n"
    path.write_text(updated)
