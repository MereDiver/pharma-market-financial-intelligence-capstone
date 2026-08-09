"""Build a source-only capstone submission ZIP with an explicit allow-list."""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = {"README.md", "databricks.yml", ".gitignore", ".env.example", "requirements-dev.txt"}
ROOT_DIRS = {"config", "pipeline", "mcp_server", "frontend", "agent", "sql", "scripts", "tests"}
EXCLUDED_PARTS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".vscode", ".idea", "data", "downloads", "delta", "screenshots", ".cache", "hf_cache"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".log", ".zip", ".csv", ".parquet"}


def included_files():
    for path in sorted(ROOT.rglob("*")):
        relative = path.relative_to(ROOT)
        if not path.is_file() or any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        if path.suffix.lower() in EXCLUDED_SUFFIXES or path.name == ".env":
            continue
        if (len(relative.parts) == 1 and path.name in ROOT_FILES) or relative.parts[0] in ROOT_DIRS:
            yield path, relative


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "pharma-market-financial-intelligence-capstone-submission.zip")
    args = parser.parse_args()
    output = args.output.resolve()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path, relative in included_files():
            archive.write(path, Path(ROOT.name) / relative)
    print(f"Created {output} ({output.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

