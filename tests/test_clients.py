from __future__ import annotations

import json

import pytest
import requests

from pipeline.cms_medicaid_client import CMSClientError, CMSMedicaidClient, normalize_header
from pipeline.openfda_client import OpenFDAClient, OpenFDAError


class Response:
    def __init__(self, status=200, payload=None, headers=None):
        self.status_code=status; self.payload=payload or {}; self.headers=headers or {}
    def raise_for_status(self):
        if self.status_code >= 400: raise requests.HTTPError(str(self.status_code))
    def json(self): return self.payload


class Session:
    def __init__(self, responses): self.responses=list(responses); self.headers={}; self.calls=[]
    def get(self, url, **kwargs): self.calls.append((url,kwargs)); return self.responses.pop(0)


def test_cms_exact_server_filter_and_pagination():
    session=Session([Response(payload={"results":[{"State Code":"CA","NDC":"1"}],"count":2}),
                     Response(payload={"results":[{"state":"CA","ndc":"2"}],"count":2})])
    client=CMSMedicaidClient(session=session,page_size=100)
    pages=list(client.iter_api_pages("dataset", "CA"))
    assert pages[0][0]["state"] == "CA"
    assert session.calls[0][1]["params"]["conditions[0][property]"] == "state"
    assert session.calls[1][1]["params"]["offset"] == 1
    assert normalize_header("No. of Prescriptions") == "number_of_prescriptions"


def test_cms_malformed_payload():
    client=CMSMedicaidClient(session=Session([Response(payload={"results":"bad"})]),page_size=100)
    with pytest.raises(CMSClientError): list(client.iter_api_pages("dataset","CA"))


def test_cms_rejects_page_sizes_above_api_maximum():
    with pytest.raises(ValueError, match="maximum of 5000"):
        CMSMedicaidClient(page_size=5001)


def ndc_result():
    return {"brand_name":"Example","generic_name":"example ingredient","packaging":[{"package_ndc":"1234-5678-90"}],"openfda":{"manufacturer_name":["Example Labs"]}}


def test_openfda_exact_match_and_missing_product(monkeypatch):
    monkeypatch.setattr("pipeline.openfda_client.time.sleep", lambda _: None)
    client=OpenFDAClient(session=Session([Response(payload={"results":[ndc_result()]})]))
    result=client.match_ndc("01234567890")
    assert result["match_status"] == "matched"
    missing=OpenFDAClient(session=Session([Response(404),Response(404),Response(404)]))
    assert missing.match_ndc("01234567890")["match_status"] == "unmatched"


def test_openfda_malformed_timeout_rate_limit_and_5xx(monkeypatch):
    monkeypatch.setattr("pipeline.openfda_client.time.sleep", lambda _: None)
    malformed=OpenFDAClient(session=Session([Response(payload={"wrong":[]})]),max_retries=0)
    with pytest.raises(OpenFDAError): malformed._request("url","search")
    timeout_session=Session([])
    timeout_session.get=lambda *a,**k: (_ for _ in ()).throw(requests.Timeout())
    with pytest.raises(OpenFDAError): OpenFDAClient(session=timeout_session,max_retries=0)._request("url","search")
    for status in (429,500):
        with pytest.raises(OpenFDAError): OpenFDAClient(session=Session([Response(status)]),max_retries=0)._request("url","search")
