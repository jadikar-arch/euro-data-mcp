"""Statistics Finland (StatFin): PxWeb API at https://pxdata.stat.fi/PxWeb/api/v1/en/StatFin."""

from __future__ import annotations

from ...pxweb import PxSource
from . import SYNONYMS


def page(table_id: str) -> str:
    folders, _, table = table_id.rpartition("/")
    return f"https://pxdata.stat.fi/PxWeb/pxweb/en/StatFin/StatFin__{'__'.join(folders.split('/'))}/{table}/"


SRC = PxSource(
    prefix="statfin",
    name="StatFin",
    agency="Statistics Finland",
    country="Finland",
    local="Finnish",
    base="https://pxdata.stat.fi/PxWeb/api/v1/en/StatFin",
    licence="CC BY 4.0, © Statistics Finland",
    page=page,
    synonyms=SYNONYMS,
    aliases={},
    min_interval=1.05,
    listing=True,
    per_minute=24,
)
