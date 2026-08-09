# Agent Bricks setup

1. Deploy the MCP App from `mcp_server/` as `mcp-pharma-intelligence` and verify `<app-url>/mcp`.
2. Attach the existing Lakebase database with resource key `postgres` and **Can connect and create**. Attach the existing SQL Warehouse with key `sql-warehouse` and **Can use**.
3. Grant the MCP App identity `USE CATALOG`, `USE SCHEMA`, and `SELECT` only on the four required Gold tables plus permission to use the dedicated Lakebase schema/tables. Do not grant Gold write privileges.
4. Register the deployed streamable-HTTP endpoint as a custom MCP server using the same UI workflow as Day 3 (or select the MCP App directly where offered).
5. Create a Supervisor/Agent Bricks agent, add all tools in `tool_manifest.md`, and paste `system_prompt.md` as its complete instructions.
6. Test `demo_questions.md`, checking product ambiguity, suppression language, decomposition reconciliation, and explicit-write behavior.
7. Deploy/save the Agent endpoint. Do not hardcode its name; attach it to the frontend App using resource key `finance-agent` with **Can query**.

Workspace UI labels change. The invariant is: custom MCP endpoint `/mcp` → governed tools → prompt → deployed Agent endpoint.

