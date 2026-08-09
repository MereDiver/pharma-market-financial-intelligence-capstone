"""Validated, non-secret configuration shared by pipeline components."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

CMS_DATASETS = {
    2024: {
        "dataset_id": "61729e5a-7aa8-448c-8903-ba3e0cd0ea3c",
        "bulk_url": "https://download.medicaid.gov/data/sdud2024_updatedJuly2026.csv",
    },
    2025: {
        "dataset_id": "158a1baa-5506-400a-8ec3-97756f0b0536",
        "bulk_url": "https://download.medicaid.gov/data/sdud2025_updatedjuly2026.csv",
    },
}
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_STATE = re.compile(r"^[A-Z]{2}$")


def _csv_ints(name: str, default: str) -> tuple[int, ...]:
    try:
        values = tuple(dict.fromkeys(int(value.strip()) for value in os.getenv(name, default).split(",") if value.strip()))
    except ValueError as exc:
        raise ValueError(f"{name} must be a comma-separated integer list.") from exc
    if not values:
        raise ValueError(f"{name} cannot be empty.")
    return values


def _states() -> tuple[str, ...]:
    values = tuple(dict.fromkeys(value.strip().upper() for value in os.getenv("MEDICAID_STATES", "CA").split(",") if value.strip()))
    if not values or any(not _STATE.fullmatch(value) for value in values):
        raise ValueError("MEDICAID_STATES must contain two-letter state codes.")
    return values


def _identifier(name: str, default: str) -> str:
    value = os.getenv(name, default).strip()
    if not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{name} must be an unquoted SQL identifier.")
    return value


@dataclass(frozen=True)
class ProjectConfig:
    catalog: str
    schema: str
    volume: str
    states: tuple[str, ...]
    years: tuple[int, ...]
    cms_mode: str
    cms_page_size: int
    cms_write_batch_size: int
    max_openfda_products: int
    app_schema: str
    embedding_model_name: str
    chunk_size: int
    chunk_overlap: int

    @property
    def table_prefix(self) -> str:
        return f"{self.catalog}.{self.schema}"


def load_config() -> ProjectConfig:
    mode = os.getenv("CMS_MODE", "api").strip().lower()
    if mode not in {"api", "bulk_csv"}:
        raise ValueError("CMS_MODE must be api or bulk_csv.")
    years = _csv_ints("MEDICAID_YEARS", "2024,2025")
    unsupported = sorted(set(years) - CMS_DATASETS.keys())
    if unsupported:
        raise ValueError(f"No CMS dataset configured for years: {unsupported}")
    page_size = int(os.getenv("CMS_PAGE_SIZE", "5000"))
    write_batch_size = int(os.getenv("CMS_WRITE_BATCH_SIZE", "50000"))
    maximum = int(os.getenv("MAX_OPENFDA_PRODUCTS", "10"))
    chunk_size = int(os.getenv("CHUNK_SIZE", "800"))
    overlap = int(os.getenv("CHUNK_OVERLAP", "100"))
    if not 100 <= page_size <= 5000:
        raise ValueError("CMS_PAGE_SIZE must be between 100 and the CMS API maximum of 5000.")
    if not page_size <= write_batch_size <= 100000:
        raise ValueError("CMS_WRITE_BATCH_SIZE must be between CMS_PAGE_SIZE and 100000.")
    if not 1 <= maximum <= 100:
        raise ValueError("MAX_OPENFDA_PRODUCTS must be between 1 and 100.")
    if chunk_size <= 0 or overlap < 0 or overlap >= chunk_size:
        raise ValueError("CHUNK_SIZE must be positive and CHUNK_OVERLAP smaller.")
    return ProjectConfig(
        catalog=_identifier("CATALOG", "workspace"),
        schema=_identifier("SCHEMA", "pharma_market_intelligence"),
        volume=_identifier("VOLUME", "pharma_pipeline"),
        states=_states(), years=years, cms_mode=mode, cms_page_size=page_size,
        cms_write_batch_size=write_batch_size,
        max_openfda_products=maximum,
        app_schema=_identifier("APP_SCHEMA", "pharma_intelligence"),
        embedding_model_name=os.getenv("EMBEDDING_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2"),
        chunk_size=chunk_size, chunk_overlap=overlap,
    )
