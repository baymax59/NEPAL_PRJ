"""Facts about each data source that the rest of the app needs, e.g. attribution text."""

from app.connectors.sc_judgments import source as sc_judgments

# Shown wherever a source's data is displayed (required by CC-BY for the Supreme Court data).
ATTRIBUTIONS: dict[str, str] = {
    sc_judgments.SOURCE_SYSTEM: sc_judgments.ATTRIBUTION,
}


def attribution_for(source_system: str) -> str | None:
    return ATTRIBUTIONS.get(source_system)
