"""Shared setup for the walkthrough notebooks in this folder.

Every notebook starts with:

    LIVE = False   # False: recorded responses and local files, no cost. True: real Google Cloud calls.
    from nb_setup import setup, short, table, module, functions
    SUBMISSION = setup(live=LIVE)

What setup() does, in the order a script would get it from `source env.sh`:
1. finds submission/ (the folder with env.sh) from wherever the notebook runs;
2. loads every variable env.sh exports into os.environ (a notebook cannot `source` a file,
   and src/config.py stops at import if GOOGLE_CLOUD_PROJECT is missing: fail fast);
3. puts src/ and harness/ on the import path, like the scripts do;
4. chooses the mode: MEDEVIDENCE_OFFLINE=1 replays the recorded responses in
   tests/fixtures/runtime/ (no Google client is created at all), 0 calls Google Cloud;
5. tags this traffic (MEDEVIDENCE_RUN_TAG=notebook), so the health report counts it as test use.
"""

from __future__ import annotations

import importlib
import inspect
import os
import re
import subprocess
import sys
import warnings
from pathlib import Path


def _submission() -> Path:
    here = Path.cwd().resolve()
    for folder in [here, *here.parents]:
        if (folder / "env.sh").exists() and (folder / "src").is_dir():
            return folder
    raise SystemExit("Open the notebook from inside submission/ (no env.sh found above this folder).")


def setup(live: bool = False, run_tag: str = "notebook") -> Path:
    root = _submission()
    env_file = root / "env.sh"
    names = re.findall(r"^\s*export\s+([A-Za-z_][A-Za-z0-9_]*)=", env_file.read_text(encoding="utf-8"), flags=re.M)
    dump = subprocess.run(["bash", "-c", f"source '{env_file}' >/dev/null 2>&1 && env -0"],
                          capture_output=True, text=True, check=True).stdout
    values = dict(item.split("=", 1) for item in dump.split("\0") if "=" in item)
    for name in names:  # only the variables env.sh defines
        if name in values:
            os.environ[name] = values[name]
    os.environ["MEDEVIDENCE_OFFLINE"] = "0" if live else "1"
    os.environ["MEDEVIDENCE_RUN_TAG"] = run_tag
    warnings.filterwarnings("ignore", message=r".*\[EXPERIMENTAL\].*")  # ADK feature notices, not errors
    for sub in ("harness", "src"):
        path = str(root / sub)
        if path not in sys.path:
            sys.path.insert(0, path)
    mode = "LIVE: real Google Cloud calls (small cost)" if live else "OFFLINE: recorded responses, no cost"
    print(f"submission : {root}")
    print(f"mode       : {mode}")
    print(f"project    : {os.environ.get('GOOGLE_CLOUD_PROJECT')} · answers: {os.environ.get('GENERATION_MODEL')}"
          f" · agent: {os.environ.get('AGENT_MODEL')} · embeddings: {os.environ.get('EMBEDDING_MODEL')}")
    return root


def module(name: str):
    """Import a script whose file name starts with a digit (01_load_tables.py → module('01_load_tables'))."""
    return importlib.import_module(name)


def functions(mod):
    """Every function defined in a module, in file order, with the first line of its docstring: a map
    of the file before walking through it."""
    rows = []
    for name, fn in inspect.getmembers(mod, inspect.isfunction):
        if fn.__module__ == mod.__name__:
            doc = (inspect.getdoc(fn) or "").split("\n")[0]
            rows.append({"line": inspect.getsourcelines(fn)[1], "function": name, "what it does": doc})
    return table(sorted(rows, key=lambda r: r["line"]), width=120)


def short(text, n: int = 300) -> str:
    """One line, at most n characters: newlines shown as ⏎."""
    text = str(text).replace("\n", " ⏎ ")
    return text if len(text) <= n else text[:n] + " …"


def table(rows: list[dict], columns: list[str] | None = None, width: int = 80):
    """Rows as a pandas DataFrame, long text cut to `width` characters, so a cell stays readable."""
    import pandas as pd

    frame = pd.DataFrame(rows)
    if columns:
        frame = frame[[c for c in columns if c in frame.columns]]
    for col in frame.columns:
        if frame[col].dtype == object:
            frame[col] = frame[col].map(lambda v: short(v, width) if isinstance(v, str) else v)
    return frame
