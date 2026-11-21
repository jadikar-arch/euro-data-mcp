"""Statistics Sweden (SCB): PxWeb API at https://api.scb.se/OV0104/v1/doris/en/ssd."""

from __future__ import annotations

from ...pxweb import PxSource
from . import SYNONYMS

CKM = (
    "this table uses SCB's Cell Key Method: counts are randomly adjusted by up to ±3, so totals may not equal "
    "the sum of their parts, and small numbers are uncertain"
)


def note(table_id: str) -> str:
    return CKM if table_id.endswith("CKM") else ""


def page(table_id: str) -> str:
    folders, _, table = table_id.rpartition("/")
    return f"https://www.statistikdatabasen.scb.se/pxweb/en/ssd/START__{'__'.join(folders.split('/'))}/{table}/"


SRC = PxSource(
    prefix="scb",
    name="SCB",
    agency="Statistics Sweden",
    country="Sweden",
    local="Swedish",
    base="https://api.scb.se/OV0104/v1/doris/en/ssd",
    licence="CC0 1.0, Statistics Sweden (SCB)",
    page=page,
    note=note,
    synonyms=SYNONYMS,
    aliases={"gothenburg": "goteborg"},
    min_interval=1.05,
    per_minute=55,
)
