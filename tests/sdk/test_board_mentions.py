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
async def test_post_message_success(context):
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = MagicMock(status_code=201)
        
        result = await post_message("Hello @agent-1")
        
        assert "Message posted to thread T1" in result
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert kwargs["json"]["from_agent"] == "test-agent"
        assert kwargs["json"]["message"] == "Hello @agent-1"

@pytest.mark.asyncio
async def test_post_message_mention_error(context):
    # Simulate server returning a mention error
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = MagicMock(
            status_code=400, 
            json=lambda: {"error": "NO_RECIPIENT"}
        )
        
        result = await post_message("Hello world") # No mentions
        
        assert "Error: NO_RECIPIENT" in result
        mock_post.assert_called_once()
