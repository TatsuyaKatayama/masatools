import pytest

from mcp.shared.memory import create_connected_server_and_client_session

from masatools.adapters.mcp.server import mcp
from masatools.core.context import AgentContext

@pytest.mark.asyncio
async def test_mcp_server_connection_and_tools():
    """
    IT-MCP-006: MCP サーバーの正常起動とツール公開のテスト
    """
    async with create_connected_server_and_client_session(mcp) as session:
        tools_result = await session.list_tools()
        tools = tools_result.tools
        tool_names = [t.name for t in tools]

        expected_tools = [
            "check_board_tool",
            "post_response_tool",
            "create_thread_tool",
            "sync_from_s3_tool",
            "sync_to_s3_tool",
            "check_connectivity_tool",
        ]
        for ext in expected_tools:
            assert ext in tool_names, f"Tool {ext} not found in MCP server"

        assert "update_status_tool" not in tool_names

@pytest.mark.asyncio
async def test_mcp_check_connectivity_tool(monkeypatch):
    """
    IT-MCP-008: check_connectivity_tool の動作確認 (接続エラー時)
    """
    import httpx
    import masatools.core

    async def fail_nats_client(**_kwargs):
        raise TimeoutError("NATS unavailable")

    class FailingS3:
        class Client:
            def list_buckets(self):
                raise TimeoutError("S3 unavailable")

        s3 = Client()

    async def fail_get(*_args, **_kwargs):
        raise httpx.ConnectError("API unavailable")

    monkeypatch.setattr(
        masatools.core,
        "get_default_context",
        lambda: AgentContext(
            agent_id="test-agent",
            nats_url="nats://test.invalid:4222",
            api_url="http://test.invalid/api/v1",
            s3_endpoint="http://test.invalid/s3",
        ),
    )
    monkeypatch.setattr(masatools.core, "get_nats_client", fail_nats_client)
    monkeypatch.setattr(masatools.core, "get_s3_client", lambda: FailingS3())
    monkeypatch.setattr(httpx.AsyncClient, "get", fail_get)

    async with create_connected_server_and_client_session(mcp) as session:
        result = await session.call_tool("check_connectivity_tool", arguments={})
        content = str(result.content)
        print(f"Connectivity check output: {content}")

        assert "NATS" in content
        assert "API" in content
        assert "S3" in content

@pytest.mark.asyncio
async def test_mcp_tool_execution_logic_mcp_level():
    """
    IT-MCP-007: プロトコルレベルのツール実行テスト
    """
    async with create_connected_server_and_client_session(mcp) as session:
        print("\n--- Testing non-existent tool ---")
        try:
            await session.call_tool("non_existent_tool", arguments={})
            print("Warning: Call succeeded for non-existent tool (unexpected)")
        except Exception as e:
            print(f"Captured error for non-existent tool: {type(e).__name__}: {str(e)}")
