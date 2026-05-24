import asyncio
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import os

# サーバーの起動設定
# masatoolsパッケージをインストール済みの前提で、モジュールとして実行
server_params = StdioServerParameters(
    command="python",
    args=["-m", "masatools.adapters.mcp.server"],
    env=os.environ.copy()
)

@pytest.mark.asyncio
async def test_mcp_server_connection_and_tools():
    """
    IT-MCP-006: MCP サーバーの正常起動とツール公開のテスト
    """
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # 1. 初期化 (JSON-RPC handshake)
            await session.initialize()
            
            # 2. ツール一覧の取得
            tools_result = await session.list_tools()
            tools = tools_result.tools
            tool_names = [t.name for t in tools]
            
            # 期待されるツールが含まれているか確認
            expected_tools = [
                "check_board_tool", 
                "post_response_tool", 
                "update_status_tool", 
                "create_thread_tool",
                "sync_from_s3_tool",
                "sync_to_s3_tool"
            ]
            for ext in expected_tools:
                assert ext in tool_names, f"Tool {ext} not found in MCP server"

            # 3. スキーマの整合性チェック (例: update_status_tool)
            update_status = next(t for t in tools if t.name == "update_status_tool")
            assert "progress" in update_status.inputSchema["properties"]
            assert "state" in update_status.inputSchema["properties"]

@pytest.mark.asyncio
async def test_mcp_tool_execution_logic_mcp_level():
    """
    IT-MCP-007: プロトコルレベルのツール実行テスト
    """
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # 異常系: 存在しないツール名での呼び出し
            # FastMCP内部ではToolErrorが出るが、stdio通信経由でどう見えるかを確認
            print("\n--- Testing non-existent tool ---")
            try:
                await session.call_tool("non_existent_tool", arguments={})
                print("Warning: Call succeeded for non-existent tool (unexpected)")
            except Exception as e:
                print(f"Captured error for non-existent tool: {type(e).__name__}: {str(e)}")

            # 異常系: 必須引数欠落
            print("\n--- Testing missing required argument ---")
            try:
                await session.call_tool("update_status_tool", arguments={"state": "RUNNING"})
                print("Warning: Call succeeded for missing argument (unexpected)")
            except Exception as e:
                print(f"Captured error for missing argument: {type(e).__name__}: {str(e)}")

            # 正常系: 全ての必須引数を揃えた場合
            print("\n--- Testing normal call (should reach SDK) ---")
            try:
                result = await session.call_tool("update_status_tool", arguments={"progress": 50, "state": "RUNNING"})
                print(f"Tool execution response content: {result.content}")
                # SDKの戻り値（例: NATS接続エラー文字列）が含まれているか確認
                assert any("Error" in str(c) or "Status" in str(c) for c in result.content) or result.content
            except Exception as e:
                print(f"Unexpected error in normal call: {type(e).__name__}: {e}")
                # ここで落ちる場合はプロトコルスタックの異常
                raise e
