"""Bounded official CMS Medicaid API and streaming bulk-CSV ingestion client."""

from __future__ import annotations

import csv
import io
import random
import re
import time
from collections.abc import Iterator
from typing import Any

import requests

API_TEMPLATE = "https://data.medicaid.gov/api/1/datastore/query/{dataset_id}/0"


def normalize_header(value: str) -> str:
    """Normalize evolving source headings without assuming exact CSV spelling."""
    cleaned = re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")
    aliases = {
        "record_id": "utilization_type", "state_code": "state",
        "product_fda_list_name": "product_name", "no_of_prescriptions": "number_of_prescriptions",
    }
    return aliases.get(cleaned, cleaned)


def normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    return {normalize_header(key): value for key, value in record.items()}


class CMSClientError(RuntimeError):
    """The official CMS source could not be read safely."""


class CMSMedicaidClient:
    def __init__(self, *, session: requests.Session | None = None, page_size: int = 5000,
                 timeout: tuple[float, float] = (10, 90), max_retries: int = 4) -> None:
        if not 100 <= page_size <= 5000:
            raise ValueError("page_size must be between 100 and the CMS API maximum of 5000")
        self.session = session or requests.Session()
        self.page_size = page_size
        self.timeout = timeout
        self.max_retries = max_retries
        self.session.headers.update({"User-Agent": "pharma-market-financial-intelligence-capstone/1.0"})

    def _get(self, url: str, *, params: dict[str, Any] | None = None, stream: bool = False) -> requests.Response:
        for attempt in range(self.max_retries + 1):
            try:
                response = self.session.get(url, params=params, timeout=self.timeout, stream=stream)
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt == self.max_retries:
                        response.raise_for_status()
                    retry_after = response.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after and retry_after.isdigit() else min(16.0, 2**attempt + random.random())
                    time.sleep(delay)
                    continue
                response.raise_for_status()
                return response
            except (requests.Timeout, requests.ConnectionError) as exc:
                if attempt == self.max_retries:
                    raise CMSClientError("CMS request failed after bounded retries.") from exc
                time.sleep(min(16.0, 2**attempt + random.random()))
        raise CMSClientError("CMS request failed.")

    def iter_api_pages(self, dataset_id: str, state: str) -> Iterator[list[dict[str, Any]]]:
        """Yield one official API page at a time using documented limit/offset and a state condition."""
        offset = 0
        url = API_TEMPLATE.format(dataset_id=dataset_id)
        while True:
            params = {
                "conditions[0][property]": "state",
                "conditions[0][value]": state,
                "limit": self.page_size,
                "offset": offset,
            }
            payload = self._get(url, params=params).json()
            records = payload.get("results")
            if not isinstance(records, list):
                raise CMSClientError("CMS returned a malformed datastore payload.")
            if records:
                yield [normalize_record(row) for row in records]
            offset += len(records)
            count = int(payload.get("count", offset))
            if not records or offset >= count:
                break

    def iter_bulk_batches(self, bulk_url: str, states: set[str]) -> Iterator[list[dict[str, Any]]]:
        """Stream an annual CSV and retain only configured states in bounded batches."""
        response = self._get(bulk_url, stream=True)
        response.raw.decode_content = True
        wrapper = io.TextIOWrapper(response.raw, encoding="utf-8-sig", newline="")
        reader = csv.DictReader(wrapper)
        batch: list[dict[str, Any]] = []
        try:
            for raw in reader:
                record = normalize_record(raw)
                if str(record.get("state", "")).strip().upper() not in states:
                    continue
                batch.append(record)
                if len(batch) >= self.page_size:
                    yield batch
                    batch = []
            if batch:
                yield batch
        finally:
            wrapper.close()
            response.close()
