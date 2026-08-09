"""OAuth-authenticated invocation of the attached Agent endpoint."""

from __future__ import annotations

import os
from typing import Any

from databricks.sdk import WorkspaceClient


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
        body={"input": [{"role": "user", "content": prompt}]},
    )
    if not isinstance(response, dict):
        return {"answer": str(response), "raw": response}
    answer = _extract_answer(response)
    return {"answer": answer or "The agent returned no displayable answer.", "raw": response}
