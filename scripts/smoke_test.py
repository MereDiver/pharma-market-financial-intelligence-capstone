"""Static, offline acceptance smoke test for required repository capabilities."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    required = ["README.md", "databricks.yml", "pipeline", "mcp_server", "frontend", "agent"]
    missing = [name for name in required if not (ROOT / name).exists()]
    if missing:
        raise SystemExit("Missing required capstone paths: " + ", ".join(missing))
    forbidden = {"day1-lakebase-support-app-submission", "databricks-lakebase-app-day-2-adri", "databricks-lakebase-app-day-3-adri-top"}
    nested = [path for path in ROOT.rglob("*") if path.is_dir() and path.name.lower() in forbidden]
    if nested:
        raise SystemExit("Reference assignment nested in capstone: " + str(nested[0]))
    checks = {
        "Spark pipeline": "SparkSession",
        "openFDA": "api.fda.gov",
        "FastMCP": "FastMCP",
        "Agent write": "save_investigation",
        "Frontend": "Ask Pharma Finance",
        "pgvector": "VECTOR(384)",
    }
    corpus = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in ROOT.rglob("*") if path.is_file() and path.suffix in {".py", ".md", ".sql", ".html"})
    absent = [name for name, marker in checks.items() if marker not in corpus]
    if absent:
        raise SystemExit("Capability markers absent: " + ", ".join(absent))
    print("Offline smoke test passed: required root and all five capstone capabilities are present.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

