"""OAuth-authenticated invocation of the attached Agent endpoint."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any

from databricks.sdk import WorkspaceClient

READ_ONLY_TOOLS = {
    "get_market_overview",
    "get_product_performance",
    "get_variance_drivers",
    "decompose_reimbursement_change",
    "detect_reimbursement_outliers",
    "get_drug_profile",
    "search_drug_context",
}
MAX_APPROVAL_ROUNDS = 10
APPROVAL_TTL_SECONDS = 15 * 60


def _approval_requests(response: dict[str, Any]) -> list[dict[str, Any]]:
    output = response.get("output")
    if not isinstance(output, list):
        return []
    return [
        item for item in output
        if isinstance(item, dict) and item.get("type") == "mcp_approval_request"
    ]


def _extract_answer(response: dict[str, Any]) -> str | None:
    """Extract assistant text from Responses API and legacy endpoint payloads."""
    output_text = response.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    output = response.get("output")
    if isinstance(output, str) and output.strip():
        return output
    if isinstance(output, list):
        text_parts: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if isinstance(content, str):
                text_parts.append(content)
                continue
            if not isinstance(content, list):
                continue
            for part in content:
                if isinstance(part, str):
                    text_parts.append(part)
                elif isinstance(part, dict) and isinstance(part.get("text"), str):
                    text_parts.append(part["text"])
        if text_parts:
            return "\n".join(part for part in text_parts if part.strip())

    choices = response.get("choices") or []
    if choices and isinstance(choices[0], dict):
        return (choices[0].get("message") or {}).get("content") or choices[0].get("text")
    content = response.get("content")
    answer = response.get("answer")
    return content if isinstance(content, str) else answer if isinstance(answer, str) else None


def _signing_key() -> bytes:
    key = os.getenv("APPROVAL_SIGNING_KEY") or os.getenv("DATABRICKS_CLIENT_SECRET")
    if not key:
        raise RuntimeError("The App runtime approval-signing credential is unavailable.")
    return key.encode("utf-8")


def _encode_approval(context: dict[str, Any]) -> str:
    payload = json.dumps(context, separators=(",", ":"), sort_keys=True).encode("utf-8")
    signature = hmac.new(_signing_key(), payload, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(signature + payload).decode("ascii")


def _decode_approval(token: str) -> dict[str, Any]:
    try:
        signed = base64.b64decode(str(token), altchars=b"-_", validate=True)
        signature, payload = signed[:32], signed[32:]
        expected = hmac.new(_signing_key(), payload, hashlib.sha256).digest()
        if len(signature) != 32 or not hmac.compare_digest(signature, expected):
            raise ValueError
        context = json.loads(payload)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("The write approval is invalid. Start the investigation again.") from exc
    issued_at = context.get("issued_at")
    if not isinstance(issued_at, int) or not 0 <= time.time() - issued_at <= APPROVAL_TTL_SECONDS:
        raise ValueError("The write approval expired. Start the investigation again.")
    if not isinstance(context.get("history"), list) or not isinstance(context.get("approvals"), list):
        raise ValueError("The write approval is invalid. Start the investigation again.")
    return context


def _approval_result(endpoint: str, history: list[dict[str, Any]],
                     approvals: list[dict[str, Any]]) -> dict[str, Any]:
    proposed = [
        {
            "id": request.get("id"),
            "name": request.get("name", "unknown"),
            "server_label": request.get("server_label"),
            "arguments": request.get("arguments", "{}"),
        }
        for request in approvals
    ]
    token = _encode_approval({
        "issued_at": int(time.time()),
        "endpoint": endpoint,
        "history": history,
        "approvals": proposed,
    })
    names = ", ".join(str(request["name"]) for request in proposed)
    return {
        "answer": f"Review and approve the proposed write: {names}.",
        "approval_required": True,
        "approval_token": token,
        "proposed_writes": proposed,
    }


def _run_agent(endpoint: str, history: list[dict[str, Any]]) -> dict[str, Any]:
    client = WorkspaceClient()
    path = f"/serving-endpoints/{endpoint}/invocations"
    response: Any = None
    for _ in range(MAX_APPROVAL_ROUNDS):
        response = client.api_client.do("POST", path, body={"input": history})
        if not isinstance(response, dict):
            return {"answer": str(response), "raw": response}
        approvals = _approval_requests(response)
        if not approvals:
            break
        output = response.get("output") or []
        history.extend(item for item in output if isinstance(item, dict))
        protected = [request for request in approvals if request.get("name") not in READ_ONLY_TOOLS]
        read_only = [request for request in approvals if request.get("name") in READ_ONLY_TOOLS]
        history.extend(
            {
                "type": "mcp_approval_response",
                "id": request["id"],
                "approval_request_id": request["id"],
                "approve": True,
            }
            for request in read_only
        )
        if protected:
            return _approval_result(endpoint, history, protected)
    else:
        raise RuntimeError("The agent exceeded the maximum number of MCP approval rounds.")

    answer = _extract_answer(response)
    return {"answer": answer or "The agent returned no displayable answer.", "raw": response}


def ask_agent(message: str) -> dict[str, Any]:
    endpoint = os.getenv("AGENT_ENDPOINT")
    if not endpoint:
        raise RuntimeError("AGENT_ENDPOINT is not configured from the finance-agent App resource.")
    prompt = " ".join(str(message or "").split())
    if not prompt or len(prompt) > 8000:
        raise ValueError("Question must be between 1 and 8000 characters.")
    return _run_agent(endpoint, [{"role": "user", "content": prompt}])


def continue_agent(approval_token: str, approve: bool) -> dict[str, Any]:
    context = _decode_approval(approval_token)
    endpoint = os.getenv("AGENT_ENDPOINT")
    if not endpoint or context.get("endpoint") != endpoint:
        raise ValueError("The Agent endpoint changed. Start the investigation again.")
    if not approve:
        return {"answer": "The proposed write was cancelled.", "approval_cancelled": True}
    history = context["history"]
    for request in context["approvals"]:
        request_id = request.get("id")
        if not isinstance(request_id, str) or not request_id:
            raise ValueError("The write approval is invalid. Start the investigation again.")
        history.append({
            "type": "mcp_approval_response",
            "id": request_id,
            "approval_request_id": request_id,
            "approve": True,
        })
    return _run_agent(endpoint, history)
