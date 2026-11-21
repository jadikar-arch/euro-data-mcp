"""Statistics Estonia (StatEE): PxWeb API at https://andmed.stat.ee/api/v1/en/stat."""

from __future__ import annotations

from ...pxweb import PxSource
from . import SYNONYMS


def page(table_id: str) -> str:
    folders, _, table = table_id.rpartition("/")
    return f"https://andmed.stat.ee/en/stat/{'__'.join(folders.split('/'))}/{table}"


SRC = PxSource(
    prefix="statee",
    name="StatEE",
    agency="Statistics Estonia",
    country="Estonia",
    local="Estonian",
    base="https://andmed.stat.ee/api/v1/en/stat",
    licence="CC BY-SA 4.0, © Statistics Estonia (Statistikaamet)",
    page=page,
    synonyms=SYNONYMS,
    aliases={},
    min_interval=0.06,
    listing=True,
    archive=lambda tid: tid.startswith("Lepetatud_tabelid/"),
)
