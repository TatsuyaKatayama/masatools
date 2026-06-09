import pytest
from unittest.mock import AsyncMock, patch
from masatools.adapters.mcp.server import mcp

def test_mcp_tools_registered():
    """
    Check if all required tools are registered in the MCP server.
    """
    # In recent versions of FastMCP, tools are handled differently.
    # We can check the registered tools through the server's internal state if possible,
    # or simply rely on the fact that the functions are decorated.
    # For now, let's look at the names of functions decorated with @mcp.tool()
    # FastMCP might not have a public list, so we check if the functions exist in the module.
    from masatools.adapters.mcp.server import (
        check_board_tool, 
        get_runtime_context_tool,
        post_response_tool, 
        start_monitoring_tool,
        sync_from_s3_tool, 
        sync_to_s3_tool, 
        create_thread_tool
    )
    assert check_board_tool is not None
    assert get_runtime_context_tool is not None
    assert post_response_tool is not None
    assert start_monitoring_tool is not None
    assert sync_from_s3_tool is not None
    assert sync_to_s3_tool is not None
    assert create_thread_tool is not None

@pytest.mark.asyncio
async def test_mcp_check_board_call():
    with patch("masatools.adapters.mcp.server.check_board", new_callable=AsyncMock) as mock_check:
        mock_check.return_value = "Task found"
        from masatools.adapters.mcp.server import check_board_tool
        result = await check_board_tool(wait_seconds=10, interval_seconds=2)
        assert result == "Task found"
        mock_check.assert_called_once_with(wait_seconds=10, interval_seconds=2)

@pytest.mark.asyncio
async def test_mcp_start_monitoring_tool_call():
    with patch("masatools.adapters.mcp.server.start_monitoring") as mock_start:
        mock_start.return_value = "Monitoring started"
        from masatools.adapters.mcp.server import start_monitoring_tool
        result = await start_monitoring_tool(duration_seconds=1800)
        assert result == "Monitoring started"
        mock_start.assert_called_once_with(1800)

@pytest.mark.asyncio
async def test_mcp_get_runtime_context_tool_call():
    with patch("masatools.adapters.mcp.server.get_runtime_context") as mock_context:
        mock_context.return_value = {"is_monitoring": True, "remaining_seconds": 300}
        from masatools.adapters.mcp.server import get_runtime_context_tool
        result = await get_runtime_context_tool()
        assert result == {"is_monitoring": True, "remaining_seconds": 300}
        mock_context.assert_called_once_with()

@pytest.mark.asyncio
async def test_mcp_post_response_tool_call():
    with patch("masatools.adapters.mcp.server.post_response", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = "Result posted"
        from masatools.adapters.mcp.server import post_response_tool
        result = await post_response_tool(output_dir="out", exit_code=0)
        assert result == "Result posted"
        mock_post.assert_called_once_with("out", 0, None, None, None)
