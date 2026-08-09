"""Small-volume openFDA NDC metadata and Drug Label client."""

from __future__ import annotations

import random
import time
from typing import Any

import requests

from pipeline.ndc_utils import fda_package_ndc_candidates

NDC_URL = "https://api.fda.gov/drug/ndc.json"
LABEL_URL = "https://api.fda.gov/drug/label.json"
LABEL_SECTIONS = (
    "indications_and_usage", "purpose", "description", "dosage_and_administration",
    "warnings", "warnings_and_cautions", "contraindications", "adverse_reactions",
    "clinical_pharmacology", "mechanism_of_action", "clinical_studies",
)


class OpenFDAError(RuntimeError):
    pass


class OpenFDAClient:
    def __init__(self, api_key: str | None = None, session: requests.Session | None = None,
                 timeout: tuple[float, float] = (10, 30), max_retries: int = 3) -> None:
        self.api_key = api_key
        self.session = session or requests.Session()
        self.timeout = timeout
        self.max_retries = max_retries
        self.session.headers.update({"User-Agent": "pharma-market-financial-intelligence-capstone/1.0"})

    def _request(self, url: str, search: str) -> dict[str, Any] | None:
        params: dict[str, Any] = {"search": search, "limit": 1}
        if self.api_key:
            params["api_key"] = self.api_key
        for attempt in range(self.max_retries + 1):
            try:
                response = self.session.get(url, params=params, timeout=self.timeout)
                if response.status_code == 404:
                    return None
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt == self.max_retries:
                        response.raise_for_status()
                    time.sleep(min(8.0, 2**attempt + random.random()))
                    continue
                response.raise_for_status()
                payload = response.json()
                results = payload.get("results")
                if not isinstance(results, list):
                    raise OpenFDAError("openFDA returned a malformed payload.")
                return results[0] if results else None
            except (requests.Timeout, requests.ConnectionError) as exc:
                if attempt == self.max_retries:
                    raise OpenFDAError("openFDA timed out after bounded retries.") from exc
                time.sleep(min(8.0, 2**attempt + random.random()))
            except requests.HTTPError as exc:
                raise OpenFDAError("openFDA returned an upstream HTTP error.") from exc
            except ValueError as exc:
                raise OpenFDAError("openFDA returned malformed JSON.") from exc
        return None

    def match_ndc(self, ndc_11: str, cms_product_name: str | None = None) -> dict[str, Any]:
        for candidate in fda_package_ndc_candidates(ndc_11):
            result = self._request(NDC_URL, f'packaging.package_ndc:"{candidate}"')
            if result:
                return self._normalize_product(result, "exact_package_ndc", "matched", candidate)
        if cms_product_name and cms_product_name.strip():
            escaped = cms_product_name.strip().replace('"', "")
            result = self._request(NDC_URL, f'brand_name.exact:"{escaped}"')
            if result:
                return self._normalize_product(result, "brand_name_fallback", "fallback", None)
        return {"match_status": "unmatched", "match_method": "none", "queried_ndc_11": ndc_11}

    @staticmethod
    def _normalize_product(raw: dict[str, Any], method: str, status: str, matched_ndc: str | None) -> dict[str, Any]:
        openfda = raw.get("openfda") if isinstance(raw.get("openfda"), dict) else {}
        active = raw.get("active_ingredients") if isinstance(raw.get("active_ingredients"), list) else []
        packaging = raw.get("packaging") if isinstance(raw.get("packaging"), list) else []
        def first(value: Any) -> Any:
            return value[0] if isinstance(value, list) and value else value
        return {
            "brand_name": raw.get("brand_name"), "generic_name": raw.get("generic_name"),
            "manufacturer_name": first(openfda.get("manufacturer_name")), "dosage_form": raw.get("dosage_form"),
            "route": first(raw.get("route")), "product_type": raw.get("product_type"),
            "product_ndc": raw.get("product_ndc"),
            "package_ndc": [item.get("package_ndc") for item in packaging if isinstance(item, dict) and item.get("package_ndc")],
            "application_number": raw.get("application_number"), "spl_set_id": raw.get("spl_set_id"),
            "substance_name": first(openfda.get("substance_name")) or (active[0].get("name") if active and isinstance(active[0], dict) else None),
            "pharm_class": openfda.get("pharm_class_epc") or raw.get("pharm_class"),
            "match_method": method, "match_status": status, "matched_package_ndc": matched_ndc,
            "payload": raw,
        }

    def get_label(self, product: dict[str, Any]) -> dict[str, Any] | None:
        searches = []
        if product.get("spl_set_id"):
            searches.append(f'set_id:"{product["spl_set_id"]}"')
        if product.get("matched_package_ndc"):
            searches.append(f'openfda.package_ndc:"{product["matched_package_ndc"]}"')
        for search in searches:
            raw = self._request(LABEL_URL, search)
            if raw:
                sections: dict[str, str] = {}
                for name in LABEL_SECTIONS:
                    value = raw.get(name)
                    if isinstance(value, list):
                        text = "\n".join(str(item).strip() for item in value if str(item).strip())
                    else:
                        text = str(value).strip() if value else ""
                    if text:
                        sections[name] = text
                return {"sections": sections, "payload": raw, "source_identifier": raw.get("set_id") or product.get("spl_set_id")}
        return None
