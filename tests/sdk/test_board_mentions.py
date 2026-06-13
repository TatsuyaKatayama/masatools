import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from masatools.skills.common.board import post_message
from masatools.core.context import AgentContext
from ulid import ULID

@pytest.fixture
def context():
    with patch("masatools.skills.common.board.get_default_context") as mock_ctx:
        ctx = AgentContext(
            agent_id="test-agent",
            api_url="http://localhost:8080/api/v1",
            nats_url="nats://localhost:4222"
        )
        ctx.current_thread_id = "T1"
        mock_ctx.return_value = ctx
        yield ctx

@pytest.mark.asyncio
async def test_post_message_with_mentions_success(context):
    # Mock resolve_mentions to return a list of agents
    with patch("masatools.skills.common.board.resolve_mentions", new_callable=AsyncMock) as mock_resolve:
        mock_resolve.return_value = (["agent-1", "agent-2"], None)
        
        with patch("masatools.skills.common.board.get_nats_client", new_callable=AsyncMock) as mock_nats:
            mock_client = mock_nats.return_value
            
            result = await post_message("Hello @agent-1 @agent-2")
            
            assert "Message posted to board.result.T1" in result
            mock_resolve.assert_called_once_with("Hello @agent-1 @agent-2", "T1", context)
            # Verify to_agents is passed to publish
            mock_client.publish.assert_called_once()
            args, kwargs = mock_client.publish.call_args
            assert kwargs["to"] == ["agent-1", "agent-2"]

@pytest.mark.asyncio
async def test_post_message_with_mentions_failure(context):
    # Mock resolve_mentions to return NO_RECIPIENT
    with patch("masatools.skills.common.board.resolve_mentions", new_callable=AsyncMock) as mock_resolve:
        mock_resolve.return_value = ([], "NO_RECIPIENT")
        
        with patch("masatools.skills.common.board.get_nats_client", new_callable=AsyncMock) as mock_nats:
            mock_client = mock_nats.return_value
            
            result = await post_message("Hello world") # No mentions
            
            assert "Error: NO_RECIPIENT" in result
            mock_client.publish.assert_not_called()
