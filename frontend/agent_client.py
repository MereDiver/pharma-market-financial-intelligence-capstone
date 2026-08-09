"""OAuth-authenticated invocation of the attached Agent endpoint."""

from __future__ import annotations

import os
from typing import Any

from databricks.sdk import WorkspaceClient


def ask_agent(message: str) -> dict[str, Any]:
    endpoint = os.getenv("AGENT_ENDPOINT")
    if not endpoint:
        raise RuntimeError("AGENT_ENDPOINT is not configured from the finance-agent App resource.")
    prompt = " ".join(str(message or "").split())
    if not prompt or len(prompt) > 8000:
        raise ValueError("Question must be between 1 and 8000 characters.")
    client = WorkspaceClient()
    response = client.api_client.do(
        "POST", f"/serving-endpoints/{endpoint}/invocations",
        body={"messages": [{"role": "user", "content": prompt}]},
    )
    if not isinstance(response, dict):
        return {"answer": str(response), "raw": response}
    choices = response.get("choices") or []
    if choices and isinstance(choices[0], dict):
        answer = (choices[0].get("message") or {}).get("content") or choices[0].get("text")
    else:
        answer = response.get("output") or response.get("content") or response.get("answer")
    return {"answer": answer or "The agent returned no displayable answer.", "raw": response}

