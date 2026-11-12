"""Compute embeddings for all document chunks that don't have one yet.

Run from the backend folder (after scripts.process_documents):
    uv run python -m scripts.embed_chunks
The first run downloads the model (~130 MB) into the project's models/ folder.
"""

import argparse
import time

from app.db.session import SessionLocal
from app.embeddings.indexing import embed_pending_chunks
from app.embeddings.model import load_embedder


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--batch-size", type=int, default=64)
    args = parser.parse_args()

    started = time.perf_counter()
    embedder = load_embedder(allow_download=True)
    print(f"Model {embedder.model_name} loaded in {time.perf_counter() - started:.1f}s")

    started = time.perf_counter()
    with SessionLocal() as session:
        count = embed_pending_chunks(session, embedder, batch_size=args.batch_size)
    elapsed = time.perf_counter() - started
    rate = f" ({count / elapsed:.0f} chunks/s)" if count else ""
    print(f"Embedded {count} chunks in {elapsed:.1f}s{rate}")


if __name__ == "__main__":
    main()
