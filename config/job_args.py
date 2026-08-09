"""Map non-secret Spark Python task arguments into the central environment config."""

from __future__ import annotations

import argparse
import os


def configure_from_args() -> None:
    parser = argparse.ArgumentParser(add_help=False)
    for argument in ("catalog", "schema", "volume", "medicaid-states", "medicaid-years",
                     "cms-mode", "pg-host", "pg-database", "pg-port", "pg-sslmode",
                     "pg-user", "endpoint-name", "app-schema"):
        parser.add_argument(f"--{argument}")
    args, _ = parser.parse_known_args()
    mapping = {
        "catalog": "CATALOG", "schema": "SCHEMA", "volume": "VOLUME",
        "medicaid_states": "MEDICAID_STATES", "medicaid_years": "MEDICAID_YEARS",
        "cms_mode": "CMS_MODE", "pg_host": "PGHOST", "pg_database": "PGDATABASE",
        "pg_port": "PGPORT", "pg_sslmode": "PGSSLMODE", "pg_user": "PGUSER",
        "endpoint_name": "ENDPOINT_NAME", "app_schema": "APP_SCHEMA",
    }
    for attribute, environment_name in mapping.items():
        value = getattr(args, attribute, None)
        if value:
            os.environ[environment_name] = value

