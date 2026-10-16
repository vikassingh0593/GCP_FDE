"""Run the whole ingestion pipeline once, in order, as one health-monitored run.

    01_load_tables → 02_parse → 02a_check_parse → 03_embed_and_load (+ verify probe) → 04_create_index

Every step is safe to re-run: unchanged files are not re-parsed (cache),
unchanged chunks are not re-embedded, and tables are replaced atomically or
MERGEd. All steps share one run ID, so their checks can be read together in
BigQuery `pipeline_health`. The pipeline stops at the first failing step.

This is the code a Cloud Run service (`ingest-one`) or job would run in
production (§7); here it runs once from the terminal.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from health import current_run_id


STEPS = ["01_load_tables.py", "02_parse.py", "02a_check_parse.py", "03_embed_and_load.py", "04_create_index.py"]


def main() -> None:
    os.environ["MEDEVIDENCE_RUN_START"] = str(time.time())
    run_id = current_run_id()
    print(f"Ingestion run {run_id}\n")
    src = Path(__file__).resolve().parent
    for step in STEPS:
        started = time.time()
        print(f"===== {step}", flush=True)
        result = subprocess.run([sys.executable, str(src / step)], env=os.environ.copy())
        if result.returncode != 0:
            raise SystemExit(f"\nStopped: {step} failed (exit {result.returncode}). Run {run_id}.")
        print(f"----- {step} done in {time.time() - started:.0f}s\n", flush=True)
    total = time.time() - float(os.environ["MEDEVIDENCE_RUN_START"])
    print(f"Ingestion run {run_id} complete in {total:.0f}s (15-minute SLA: {'met' if total <= 900 else 'MISSED'}).")


if __name__ == "__main__":
    main()
