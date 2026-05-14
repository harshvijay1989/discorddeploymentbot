"""Parse a Salesforce package.xml into a structured summary (display only)."""
from __future__ import annotations

from dataclasses import dataclass
from xml.etree import ElementTree as ET

_SF_NS = "http://soap.sforce.com/2006/04/metadata"


@dataclass
class PackageInfo:
    api_version: str
    types: list[dict]   # [{"name": str, "members": [str]}]

    @property
    def component_count(self) -> int:
        return sum(len(t["members"]) for t in self.types)

    def summary_lines(self) -> list[str]:
        lines = []
        for t in self.types:
            members_preview = ", ".join(t["members"][:5])
            suffix = "…" if len(t["members"]) > 5 else ""
            lines.append(f"**{t['name']}** ({len(t['members'])}): {members_preview}{suffix}")
        return lines


def parse(xml_bytes: bytes) -> PackageInfo:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        raise ValueError(f"Invalid XML: {e}") from e

    def _text(el: ET.Element, local: str) -> str:
        child = el.find(f"{{{_SF_NS}}}{local}") or el.find(local)
        return (child.text or "").strip() if child is not None else ""

    api_version = _text(root, "version") or "59.0"
    types: list[dict] = []

    for type_el in list(root.findall(f"{{{_SF_NS}}}types")) or list(root.findall("types")):
        name = _text(type_el, "name")
        if not name:
            continue
        members = [
            (m.text or "").strip()
            for m in (list(type_el.findall(f"{{{_SF_NS}}}members")) or list(type_el.findall("members")))
            if (m.text or "").strip()
        ]
        if members:
            types.append({"name": name, "members": members})

    if not types:
        raise ValueError("package.xml contains no <types> entries")

    return PackageInfo(api_version=api_version, types=types)
