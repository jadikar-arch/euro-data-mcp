"""Central Statistical Bureau of Latvia (CSB): PxWeb API at https://data.stat.gov.lv/api/v1/en/OSP_PUB."""

from __future__ import annotations

from ...pxweb import PxSource
from . import SYNONYMS


def page(table_id: str) -> str:
    folders, _, table = table_id.rpartition("/")
    return f"https://data.stat.gov.lv/pxweb/en/OSP_PUB/START__{'__'.join(folders.split('/'))}/{table}/"


SRC = PxSource(
    prefix="csb",
    name="CSB",
    agency="Central Statistical Bureau of Latvia",
    country="Latvia",
    local="Latvian",
    base="https://data.stat.gov.lv/api/v1/en/OSP_PUB",
    licence="reuse with attribution (terms correspond to CC BY 4.0), © Central Statistical Bureau of Latvia (CSB), Official Statistics Portal",
    page=page,
    synonyms=SYNONYMS,
    aliases={},
    min_interval=0.04,
    listing=True,
    archive=lambda tid: any(seg.startswith("A_") for seg in tid.split("/")[:-1]),
)
