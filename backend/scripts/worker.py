"""The worker: runs Case Management's scheduled jobs when they are due (phase CM-7, app/casemgmt/governance/jobs.py).

    uv run python -m scripts.worker                      # keeps running; looks every CM_WORKER_INTERVAL seconds (300)
    uv run python -m scripts.worker --once               # the jobs that are due now, then stops
    uv run python -m scripts.worker --run audit_verify   # one job now, due or not

Jobs: audit_checkpoint (sign the audit chain), audit_verify (check the chain and its checkpoints), evidence_sweep
(hash every stored evidence file again). Every run is recorded and audited; a failure notifies the administrators.
In Docker it runs as its own service, "worker". Exit code 1 if a job run with --once or --run failed.
"""

import argparse
import signal
import sys
import time

from app.casemgmt.enums import JobStatus
from app.casemgmt.governance import jobs
from app.casemgmt.storage import get_evidence_store
from app.core.config import get_settings
from app.db.session import SessionLocal

stopping = False


def _stop(*_args) -> None:
    global stopping
    stopping = True


def _report(runs) -> bool:
    for run in runs:
        print(f"{run.started_at:%Y-%m-%d %H:%M:%S} UTC  {run.job:<17} {run.status}", flush=True)
    return all(run.status != JobStatus.FAILED.value for run in runs)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--once", action="store_true", help="run the jobs that are due, then stop")
    parser.add_argument("--run", choices=sorted(jobs.JOBS), help="run this job now, then stop")
    args = parser.parse_args()
    store = get_evidence_store()
    if args.run:
        with SessionLocal() as session:
            run = jobs.run(session, store, args.run)
            session.commit()
        sys.exit(0 if _report([run]) else 1)
    if args.once:
        sys.exit(0 if _report(jobs.run_due(SessionLocal, store)) else 1)

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    interval = get_settings().cm_worker_interval
    print(f"Worker started: looking for due jobs every {interval} seconds", flush=True)
    while not stopping:
        try:
            _report(jobs.run_due(SessionLocal, store))
        except Exception as error:  # e.g. the database restarting: try again at the next round
            print(f"Could not run the jobs this round: {type(error).__name__}: {error}", flush=True)
        for _ in range(interval):
            if stopping:
                break
            time.sleep(1)
    print("Worker stopped", flush=True)


if __name__ == "__main__":
    main()
