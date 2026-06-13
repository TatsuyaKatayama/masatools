import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from masatools.core.mentions import resolve_mentions
from masatools.core.context import AgentContext

@pytest.fixture
def context():
    return AgentContext(
        agent_id="test-agent",
        api_url="http://localhost:8080/api/v1",
        nats_url="nats://localhost:4222"
    )

@pytest.mark.asyncio
async def test_resolve_mentions_no_mentions(context):
    to_agents, error = await resolve_mentions("Hello world", "T1", context)
    assert error == "NO_RECIPIENT"
    assert to_agents == []

@pytest.mark.asyncio
async def test_resolve_mentions_single_agent(context):
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = MagicMock(status_code=200)
        mock_get.return_value.json.return_value = {"agent": {"id": "other-agent"}}
        
        to_agents, error = await resolve_mentions("Hello @other-agent", "T1", context)
        assert error is None
        assert to_agents == ["other-agent"]
        mock_get.assert_called_with("http://localhost:8080/api/v1/agents/other-agent")

@pytest.mark.asyncio
async def test_resolve_mentions_unknown_agent(context):
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = MagicMock(status_code=404)
        
        to_agents, error = await resolve_mentions("Hello @ghost", "T1", context)
        assert error == "UNKNOWN_MENTION"
        assert to_agents == []

@pytest.mark.asyncio
async def test_resolve_mentions_team(context):
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        def side_effect(url):
            if f"/threads/T1" in url:
                return MagicMock(status_code=200, json=lambda: {"id": "T1", "team_id": "team-a"})
            if "/teams/team-a/agents" in url:
                return MagicMock(status_code=200, json=lambda: [
                    {"id": "member-1"},
                    {"id": "member-2"},
                    {"id": "test-agent"}
                ])
            return MagicMock(status_code=404)
        
        mock_get.side_effect = side_effect
        
        to_agents, error = await resolve_mentions("Hello @team", "T1", context)
        assert error is None
        assert sorted(to_agents) == ["member-1", "member-2"]

@pytest.mark.asyncio
async def test_resolve_mentions_team_context_required(context):
    # No thread_id provided
    to_agents, error = await resolve_mentions("Hello @team", None, context)
    assert error == "TEAM_CONTEXT_REQUIRED"

@pytest.mark.asyncio
async def test_resolve_mentions_mixed(context):
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        def side_effect(url):
            if "/threads/T1" in url:
                return MagicMock(status_code=200, json=lambda: {"id": "T1", "team_id": "team-a"})
            if "/teams/team-a/agents" in url:
                return MagicMock(status_code=200, json=lambda: [{"id": "member-1"}])
            if "/agents/other" in url:
                return MagicMock(status_code=200, json=lambda: {"id": "other"})
            return MagicMock(status_code=404)
        
        mock_get.side_effect = side_effect
        
        to_agents, error = await resolve_mentions("Hello @team and @other", "T1", context)
        assert error is None
        assert sorted(to_agents) == ["member-1", "other"]

@pytest.mark.asyncio
async def test_resolve_mentions_self_only(context):
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {"id": "test-agent"})
        
        to_agents, error = await resolve_mentions("Hello @test-agent", "T1", context)
        assert error == "NO_RECIPIENT"
        assert to_agents == []
