"""Import the downloaded Supreme Court subset into the database.

Run from the backend folder (after scripts.sc_download):
    uv run python -m scripts.sc_import
Safe to run repeatedly: existing cases are updated, never duplicated.
"""

import argparse

from app.connectors.sc_judgments.connector import SupremeCourtConnector
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.ingestion.pipeline import run_import


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--years", type=int, nargs="+", help="default: every downloaded year")
    args = parser.parse_args()

    connector = SupremeCourtConnector(get_settings().data_dir, years=args.years)
    with SessionLocal() as session:
        run = run_import(session, connector, parameters={"years": connector.years})

    stats = run.stats
    print(f"Run {run.id}: {run.status}")
    print(
        f"  seen {stats['seen']} | created {stats['created']} | updated {stats['updated']} | "
        f"failed {stats['failed']} | with warnings {stats['with_warnings']}"
    )
    for failure in stats["failures"][:10]:
        print(f"  failed: {failure['source_ref']}: {failure['reason']}")


if __name__ == "__main__":
    main()
