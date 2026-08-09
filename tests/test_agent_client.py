from __future__ import annotations

from frontend import agent_client


class FakeAPIClient:
    def __init__(self, response):
        self.response = response
        self.call = None

    def do(self, method, path, body):
        self.call = (method, path, body)
        return self.response


class FakeWorkspaceClient:
    api_client = None

    def __init__(self):
        self.api_client = FakeWorkspaceClient.api_client


def test_ask_agent_uses_responses_input_and_extracts_output_text(monkeypatch):
    api_client = FakeAPIClient(
        {
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "California answer"}],
                }
            ]
        }
    )
    FakeWorkspaceClient.api_client = api_client
    monkeypatch.setenv("AGENT_ENDPOINT", "finance-supervisor")
    monkeypatch.setattr(agent_client, "WorkspaceClient", FakeWorkspaceClient)

    result = agent_client.ask_agent("  Which products?  ")

    assert api_client.call == (
        "POST",
        "/serving-endpoints/finance-supervisor/invocations",
        {"input": [{"role": "user", "content": "Which products?"}]},
    )
    assert result["answer"] == "California answer"


def test_extract_answer_supports_top_level_output_text():
    assert agent_client._extract_answer({"output_text": "Direct answer"}) == "Direct answer"
