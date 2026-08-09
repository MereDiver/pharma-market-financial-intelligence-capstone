from __future__ import annotations

import importlib
import sys
import types


class FakeFastMCP:
    def __init__(self, name): self.name=name; self.registered=[]
    def tool(self):
        def decorate(function): self.registered.append(function.__name__); return function
        return decorate


def test_fastmcp_surface_registers_governed_tools_without_network(monkeypatch):
    fake=types.ModuleType("fastmcp"); fake.FastMCP=FakeFastMCP
    monkeypatch.setitem(sys.modules,"fastmcp",fake)
    sys.modules.pop("mcp_server.finance_mcp_server",None)
    server=importlib.import_module("mcp_server.finance_mcp_server")
    assert server.mcp.name == "pharma-market-financial-intelligence"
    assert set(server.mcp.registered) == {
        "get_market_overview","get_product_performance","get_variance_drivers",
        "decompose_reimbursement_change","detect_reimbursement_outliers","get_drug_profile",
        "search_drug_context","save_investigation","add_analyst_note",
        "create_follow_up_action","update_investigation_status","update_follow_up_action",
    }
    assert not any("sql" in name for name in server.mcp.registered)

