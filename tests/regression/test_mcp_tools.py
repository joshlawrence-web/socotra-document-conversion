"""Smoke test — verify all 7 MCP tools are discoverable at startup."""
import velocity_converter.mcp_server as mcp_server


def test_tool_count():
    tools = mcp_server.mcp._tool_manager._tools
    assert len(tools) == 7, f"Expected 7 tools, got {len(tools)}: {sorted(tools)}"


def test_expected_tool_names():
    tools = mcp_server.mcp._tool_manager._tools
    expected = {
        "convert_html_to_velocity",
        "extract_velocity_tokens",
        "suggest_velocity_paths",
        "write_final_template",
        "ingest_document",
        "generate_snapshot_plugin",
        "list_velocity_paths",
    }
    assert expected == set(tools), f"Tool mismatch:\n  expected: {sorted(expected)}\n  got:      {sorted(tools)}"


def test_list_velocity_paths_returns_markdown():
    result = mcp_server.list_velocity_paths()
    assert isinstance(result, str), "Expected string result"
    assert not result.startswith("ERROR:"), f"Unexpected error: {result[:200]}"
    assert "#" in result, "Expected Markdown headings in catalog"
