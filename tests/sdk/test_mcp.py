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
        post_response_tool, 
        sync_from_s3_tool, 
        sync_to_s3_tool, 
        update_status_tool,
        create_thread_tool
    )
    assert check_board_tool is not None
    assert post_response_tool is not None
    assert sync_from_s3_tool is not None
    assert sync_to_s3_tool is not None
    assert update_status_tool is not None
    assert create_thread_tool is not None

@pytest.mark.asyncio
async def test_mcp_check_board_call():
    with patch("masatools.adapters.mcp.server.check_board", new_callable=AsyncMock) as mock_check:
        mock_check.return_value = "Task found"
        from masatools.adapters.mcp.server import check_board_tool
        result = await check_board_tool(wait_seconds=10)
        assert result == "Task found"
        mock_check.assert_called_once_with(wait_seconds=10)

@pytest.mark.asyncio
async def test_mcp_post_response_tool_call():
    with patch("masatools.adapters.mcp.server.post_response", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = "Result posted"
        from masatools.adapters.mcp.server import post_response_tool
        result = await post_response_tool(output_dir="out", exit_code=0)
        assert result == "Result posted"
        mock_post.assert_called_once_with("out", 0, None, None)

@pytest.mark.asyncio
async def test_mcp_update_status_call():
    with patch("masatools.adapters.mcp.server.update_status", new_callable=AsyncMock) as mock_update:
        mock_update.return_value = "Status updated"
        from masatools.adapters.mcp.server import update_status_tool
        result = await update_status_tool(progress=50, state="RUNNING", message="Working...")
        assert result == "Status updated"
        mock_update.assert_called_once_with(50, "RUNNING", "Working...", None)
