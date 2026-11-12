"""Where the Indian Supreme Court Judgments dataset lives and how its files are laid out.

Dataset: https://registry.opendata.aws/indian-supreme-court-judgments/ (CC-BY-4.0, Dattam Labs).
See docs/DATASET.md. Local copies mirror the bucket layout under data/raw/sc_judgments/.
"""

import re
from pathlib import PurePosixPath

SOURCE_SYSTEM = "sc_judgments"
CONNECTOR_VERSION = "0.1.0"
ATTRIBUTION = "Indian Supreme Court Judgments dataset (Dattam Labs), CC-BY-4.0"

BASE_URL = "https://indian-supreme-court-judgments.s3.ap-south-1.amazonaws.com"

# Relative to the app's data folder.
RAW_DIR = PurePosixPath("raw") / SOURCE_SYSTEM
MANIFEST_NAME = "manifest.json"

# The `path` column, e.g. "2023_16_872_887". It becomes part of a file name, so anything
# outside this pattern is refused (stops values like "../../x" escaping the data folder).
SAFE_PATH_KEY = re.compile(r"^[A-Za-z0-9_-]{1,100}$")


def metadata_key(year: int) -> str:
    return f"metadata/parquet/year={year}/metadata.parquet"


def pdf_key(year: int, path: str) -> str:
    if not SAFE_PATH_KEY.fullmatch(path):
        raise ValueError(f"Unsafe file key in source data: {path!r}")
    return f"data/pdf/year={year}/english/{path}_EN.pdf"


def url_for(key: str) -> str:
    return f"{BASE_URL}/{key}"
