"""Download a small subset of the Supreme Court judgments dataset.

Run from the backend folder:
    uv run python -m scripts.sc_download --years 2022 2023 --per-year 50
"""

import argparse

import httpx

from app.connectors.sc_judgments.download import download_subset
from app.connectors.sc_judgments.source import RAW_DIR
from app.core.config import get_settings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--years", type=int, nargs="+", default=[2022, 2023])
    parser.add_argument("--per-year", type=int, default=50, help="judgments to sample per year")
    parser.add_argument("--seed", type=int, default=42, help="random seed; same seed = same subset")
    args = parser.parse_args()

    data_dir = get_settings().data_dir
    transport = httpx.HTTPTransport(retries=3)  # retries connection failures
    with httpx.Client(transport=transport, timeout=httpx.Timeout(60.0), follow_redirects=False) as client:
        manifest = download_subset(client, data_dir, args.years, args.per_year, args.seed)

    total_mb = sum(f.size_bytes for f in manifest.pdfs.values()) / (1024 * 1024)
    print()
    print(f"Saved to:   {data_dir / RAW_DIR}")
    print(f"PDFs:       {len(manifest.pdfs)} downloaded ({total_mb:.1f} MB), {len(manifest.failed)} failed")
    for path, reason in list(manifest.failed.items())[:10]:
        print(f"  failed: {path}: {reason}")


if __name__ == "__main__":
    main()
