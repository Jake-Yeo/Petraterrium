import io
import re
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def source_buffer(source: bytes | Path | str):
    return io.BytesIO(source) if isinstance(source, bytes) else source


def shared_strings(archive: ZipFile) -> list[str]:
    path = "xl/sharedStrings.xml"
    if path not in archive.namelist():
        return []
    root = ElementTree.fromstring(archive.read(path))
    return [
        "".join(node.text or "" for node in item.iter() if local_name(node.tag) == "t")
        for item in root
        if local_name(item.tag) == "si"
    ]


def sheet_paths(archive: ZipFile) -> dict[str, str]:
    workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    relationships = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    targets = {item.attrib["Id"]: item.attrib["Target"] for item in relationships}
    paths = {}
    for sheet in workbook.iter():
        if local_name(sheet.tag) != "sheet":
            continue
        relationship_id = next(value for key, value in sheet.attrib.items() if key.endswith("}id"))
        target = targets[relationship_id].lstrip("/")
        if not target.startswith("xl/"):
            target = "xl/" + target
        paths[sheet.attrib["name"]] = target
    return paths


def column_index(reference: str) -> int:
    letters = re.match(r"[A-Z]+", reference)
    if letters is None:
        raise ValueError(f"Invalid spreadsheet cell reference: {reference}")
    result = 0
    for letter in letters.group():
        result = result * 26 + ord(letter) - ord("A") + 1
    return result - 1


def number(value: str):
    if not value:
        return None
    try:
        integer = int(value)
        return integer
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return value


def cell_value(cell, strings: list[str]):
    kind = cell.attrib.get("t")
    if kind == "inlineStr":
        return "".join(node.text or "" for node in cell.iter() if local_name(node.tag) == "t")
    raw = next(
        (node.text or "" for node in cell if local_name(node.tag) == "v"),
        "",
    )
    if kind == "s":
        return strings[int(raw)] if raw else None
    if kind in ("str", "e"):
        return raw or None
    if kind == "b":
        return raw == "1"
    return number(raw)


def read_sheet(source: bytes | Path | str, sheet_name: str):
    with ZipFile(source_buffer(source)) as archive:
        strings = shared_strings(archive)
        paths = sheet_paths(archive)
        if sheet_name not in paths:
            raise ValueError(f"Spreadsheet has no sheet named {sheet_name}")
        with archive.open(paths[sheet_name]) as stream:
            row_values = {}
            for _, element in ElementTree.iterparse(stream, events=("end",)):
                name = local_name(element.tag)
                if name == "c":
                    row_values[column_index(element.attrib["r"])] = cell_value(element, strings)
                    element.clear()
                elif name == "row":
                    if row_values:
                        last = max(row_values)
                        yield [row_values.get(index) for index in range(last + 1)]
                    else:
                        yield []
                    row_values = {}
                    element.clear()
