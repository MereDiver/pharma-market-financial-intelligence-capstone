from __future__ import annotations

from frontend import agent_client


class FakeAPIClient:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def do(self, method, path, body):
        self.calls.append((method, path, body))
        return self.responses.pop(0)


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

    assert api_client.calls == [(
        "POST",
        "/serving-endpoints/finance-supervisor/invocations",
        {"input": [{"role": "user", "content": "Which products?"}]},
    )]
    assert result["answer"] == "California answer"


def test_extract_answer_supports_top_level_output_text():
    assert agent_client._extract_answer({"output_text": "Direct answer"}) == "Direct answer"


def test_ask_agent_approves_read_only_mcp_call_and_continues(monkeypatch):
    approval = {
        "type": "mcp_approval_request",
        "id": "tool-123",
        "name": "get_variance_drivers",
        "server_label": "mcp-pharma-intelligence",
        "arguments": '{"state":"CA"}',
    }
    api_client = FakeAPIClient(
        {
            "output": [
                {"type": "message", "role": "assistant", "content": [
                    {"type": "output_text", "text": "I'll investigate."}
                ]},
                approval,
            ]
        },
        {
            "output": [{"type": "message", "role": "assistant", "content": [
                {"type": "output_text", "text": "The final evidence-based answer."}
            ]}]
        },
    )
    FakeWorkspaceClient.api_client = api_client
    monkeypatch.setenv("AGENT_ENDPOINT", "finance-supervisor")
    monkeypatch.setattr(agent_client, "WorkspaceClient", FakeWorkspaceClient)

    result = agent_client.ask_agent("Which products?")

    assert len(api_client.calls) == 2
    continuation = api_client.calls[1][2]["input"]
    assert continuation[-1] == {
        "type": "mcp_approval_response",
        "id": "tool-123",
        "approval_request_id": "tool-123",
        "approve": True,
    }
    assert result["answer"] == "The final evidence-based answer."


def test_write_tool_requires_signed_approval_then_continues(monkeypatch):
    api_client = FakeAPIClient(
        {"output": [{
            "type": "mcp_approval_request",
            "id": "write-123",
            "name": "save_investigation",
            "arguments": '{"title":"CA drivers"}',
        }]},
        {"output": [{"type": "message", "role": "assistant", "content": [
            {"type": "output_text", "text": "Investigation saved as inv-123."}
        ]}]},
    )
    FakeWorkspaceClient.api_client = api_client
    monkeypatch.setenv("AGENT_ENDPOINT", "finance-supervisor")
    monkeypatch.setenv("APPROVAL_SIGNING_KEY", "test-only-signing-key")
    monkeypatch.setattr(agent_client, "WorkspaceClient", FakeWorkspaceClient)

    result = agent_client.ask_agent("Save this investigation")

    assert result["approval_required"] is True
    assert result["proposed_writes"][0]["name"] == "save_investigation"
    assert len(api_client.calls) == 1

    completed = agent_client.continue_agent(result["approval_token"], True)

    assert completed["answer"] == "Investigation saved as inv-123."
    assert api_client.calls[1][2]["input"][-1] == {
        "type": "mcp_approval_response",
        "id": "write-123",
        "approval_request_id": "write-123",
        "approve": True,
    }


def test_write_approval_can_be_cancelled_and_cannot_be_tampered(monkeypatch):
    api_client = FakeAPIClient({"output": [{
        "type": "mcp_approval_request",
        "id": "write-123",
        "name": "save_investigation",
        "arguments": "{}",
    }]})
    FakeWorkspaceClient.api_client = api_client
    monkeypatch.setenv("AGENT_ENDPOINT", "finance-supervisor")
    monkeypatch.setenv("APPROVAL_SIGNING_KEY", "test-only-signing-key")
    monkeypatch.setattr(agent_client, "WorkspaceClient", FakeWorkspaceClient)
    result = agent_client.ask_agent("Save this investigation")

    assert agent_client.continue_agent(result["approval_token"], False)["approval_cancelled"] is True
    tampered = result["approval_token"][:-2] + "AA"
    try:
        agent_client.continue_agent(tampered, True)
    except ValueError as error:
        assert "invalid" in str(error)
    else:
        raise AssertionError("Tampered approval token was accepted")
