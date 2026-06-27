import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import masatools.skills.common.board as board
from masatools.skills.common.board import (
    check_board,
    get_runtime_context,
    post_message,
    post_response,
    wait_thread_result,
    create_thread,
    create_subthread,
    send_offer,
    send_assign,
    start_monitoring,
    request_reflection,
    submit_reflection
)
from masatools.skills.common.storage import sync_from_s3, sync_to_s3
from masatools.core.models import MessageEnvelope
from ulid import ULID

@pytest.fixture(autouse=True)
def reset_monitoring_state():
    board._monitor_started_at = None
    board._monitor_until = None
    board._monitor_duration_seconds = None

@pytest.mark.asyncio
async def test_check_board_found():
    tid = str(ULID())
    mock_envelope = MessageEnvelope(
        type="task",
        thread_id=tid,
        from_agent="server",
        payload={"command": "test"}
    )
    
    with patch("masatools.skills.common.board.get_nats_client", new_callable=AsyncMock) as mock_get_nats:
        mock_client = mock_get_nats.return_value
        mock_client.pull_task.return_value = mock_envelope
        
        result = await check_board()
        assert f"Task found: task (Thread: {tid})" in result
        mock_client.pull_task.assert_called_once()
        assert mock_client.pull_task.call_args.kwargs["target_agent_id"] == board.get_default_context().agent_id

@pytest.mark.asyncio
async def test_check_board_found_addressed_message():
    tid = str(ULID())
    mock_envelope = MessageEnvelope(
        type="result",
        thread_id=tid,
        from_agent="reviewer",
        to=["test-agent"],
        payload={"message": "please do this", "exit_code": 0}
    )

    with patch("masatools.skills.common.board.get_nats_client", new_callable=AsyncMock) as mock_get_nats:
        mock_client = mock_get_nats.return_value
        mock_client.pull_task.return_value = None
        mock_client.pull_message.return_value = mock_envelope

        result = await check_board()
        assert f"Message found: result (Thread: {tid}, From: reviewer)" in result
        mock_client.pull_task.assert_called_once()
        mock_client.pull_message.assert_called_once()
        assert mock_client.pull_message.call_args.kwargs["target_agent_id"] == board.get_default_context().agent_id

@pytest.mark.asyncio
async def test_check_board_polls_until_task_found():
    tid = str(ULID())
    mock_envelope = MessageEnvelope(
        type="task",
        thread_id=tid,
        from_agent="server",
        payload={"command": "test"}
    )

    with patch("masatools.skills.common.board.get_nats_client", new_callable=AsyncMock) as mock_get_nats, \
         patch("masatools.skills.common.board.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock_client = mock_get_nats.return_value
        mock_client.pull_task.side_effect = [None, mock_envelope]
        mock_client.pull_message.return_value = None

        result = await check_board(wait_seconds=10, interval_seconds=2)
        assert f"Task found: task (Thread: {tid})" in result
        assert mock_client.pull_task.call_count == 2
        mock_sleep.assert_called_once()
        assert mock_sleep.call_args.args[0] <= 2

@pytest.mark.asyncio
async def test_check_board_returns_no_messages_after_timeout():
    with patch("masatools.skills.common.board.get_nats_client", new_callable=AsyncMock) as mock_get_nats:
        mock_client = mock_get_nats.return_value
        mock_client.pull_task.return_value = None
        mock_client.pull_message.return_value = None

        result = await check_board(wait_seconds=0, interval_seconds=1)
        assert result == "No messages found"
        mock_client.pull_task.assert_called_once()
        mock_client.pull_message.assert_called_once()

@pytest.mark.asyncio
async def test_check_board_returns_monitoring_finished_after_expiry():
    start_monitoring(duration_seconds=0)

    with patch("masatools.skills.common.board.get_nats_client", new_callable=AsyncMock) as mock_get_nats:
        mock_client = mock_get_nats.return_value

        result = await check_board(wait_seconds=10, interval_seconds=1)
        assert result == "Monitoring finished"
        mock_client.pull_task.assert_not_called()
        mock_client.pull_message.assert_not_called()

@pytest.mark.asyncio
async def test_check_board_limits_wait_to_remaining_monitoring_time():
    start_monitoring(duration_seconds=1)

    with patch("masatools.skills.common.board.get_nats_client", new_callable=AsyncMock) as mock_get_nats, \
         patch("masatools.skills.common.board.asyncio.sleep", new_callable=AsyncMock) as mock_sleep, \
         patch("masatools.skills.common.board._remaining_seconds_value", side_effect=[1, 0]):
        mock_client = mock_get_nats.return_value
        mock_client.pull_task.return_value = None
        mock_client.pull_message.return_value = None

        result = await check_board(wait_seconds=10, interval_seconds=5)
        assert result == "Monitoring finished"
        mock_sleep.assert_called_once()
        assert mock_sleep.call_args.args[0] <= 1

@pytest.mark.asyncio
async def test_wait_thread_result_found():
    tid = str(ULID())
    mock_envelope = MessageEnvelope(
        type="result",
        thread_id=tid,
        from_agent="benchman",
        to=["reviewer"],
        payload={"message": "bench result", "exit_code": 0}
    )

    with patch("masatools.skills.common.board.get_nats_client", new_callable=AsyncMock) as mock_get_nats, \
         patch("masatools.skills.common.board.get_default_context") as mock_context:
        mock_client = mock_get_nats.return_value
        mock_client.pull_message.return_value = mock_envelope
        mock_context.return_value.agent_id = "reviewer"
        mock_context.return_value.current_thread_id = None

        result = await wait_thread_result(
            thread_id=tid,
            from_agent="benchman",
            wait_seconds=10,
            interval_seconds=2,
            message_contains="bench result",
        )

        assert f"Result found: result (Thread: {tid}, From: benchman)" in result
        mock_client.pull_message.assert_called_once()
        kwargs = mock_client.pull_message.call_args.kwargs
        assert kwargs["subject"] == f"board.result.{tid}"
        assert kwargs["target_agent_id"] == "reviewer"
        assert kwargs["from_agent"] == "benchman"
        assert kwargs["message_contains"] == "bench result"

@pytest.mark.asyncio
async def test_wait_thread_result_timeout():
    tid = str(ULID())
    with patch("masatools.skills.common.board.get_nats_client", new_callable=AsyncMock) as mock_get_nats:
        mock_client = mock_get_nats.return_value
        mock_client.pull_message.return_value = None

        result = await wait_thread_result(thread_id=tid, wait_seconds=0, interval_seconds=1)

        assert result == f"No result found for thread {tid}"
        mock_client.pull_message.assert_called_once()

@pytest.mark.asyncio
async def test_wait_thread_result_requires_thread_id():
    with patch("masatools.skills.common.board.get_default_context") as mock_context:
        mock_context.return_value.current_thread_id = None

        result = await wait_thread_result()

        assert result == "Error: No active thread_id found in context."

def test_start_monitoring_and_runtime_context():
    result = start_monitoring(duration_seconds=1800)
    context = get_runtime_context()

    assert "Monitoring started" in result
    assert context["is_monitoring"] is True
    assert context["duration_seconds"] == 1800
    assert context["monitor_started_at"] is not None
    assert context["monitor_until"] is not None
    assert context["remaining_seconds"] > 0

@pytest.mark.asyncio
async def test_post_message_success():
    tid = str(ULID())
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = MagicMock(status_code=201)
        mock_post.return_value.json.return_value = {"id": "M1"}

        result = await post_message(
            message="Implemented the requested change @manager.",
            output_dir="results/dir",
            error=None,
            metadata={"kind": "progress"},
            thread_id=tid,
            to=["manager"],
            observers=["observer-1"],
        )

        assert f"Message posted to thread {tid}" in result
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert kwargs["json"]["message"] == "Implemented the requested change @manager."
        assert kwargs["json"]["output_dir"] == "results/dir"
        assert kwargs["json"]["metadata"] == {"kind": "progress"}
        assert kwargs["json"]["to"] == ["manager"]
        assert kwargs["json"]["observers"] == ["observer-1"]

@pytest.mark.asyncio
async def test_post_message_uses_current_thread_id():
    tid = str(ULID())
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, \
         patch("masatools.skills.common.board.get_default_context") as mock_context:
        mock_post.return_value = MagicMock(status_code=201)
        mock_post.return_value.json.return_value = {"id": "M1"}
        mock_context.return_value.agent_id = "test-agent"
        mock_context.return_value.api_url = "http://localhost:8080/api/v1"
        mock_context.return_value.current_thread_id = tid

        result = await post_message(message="Using current thread @manager.")

        assert f"Message posted to thread {tid}" in result
        mock_post.assert_called_once()

@pytest.mark.asyncio
async def test_post_message_requires_message():
    result = await post_message(message="  ", thread_id=str(ULID()))
    assert result == "Error: message is required."

@pytest.mark.asyncio
async def test_post_message_requires_thread_id():
    with patch("masatools.skills.common.board.get_nats_client", new_callable=AsyncMock), \
         patch("masatools.skills.common.board.get_default_context") as mock_context:
        mock_context.return_value.current_thread_id = None

        result = await post_message(message="No thread.")

        assert result == "Error: No active thread_id found in context."

@pytest.mark.asyncio
async def test_post_response_success():
    tid = str(ULID())
    with patch("masatools.skills.common.board.get_nats_client", new_callable=AsyncMock) as mock_get_nats:
        mock_client = mock_get_nats.return_value
        
        result = await post_response("results/dir", exit_code=0, thread_id=tid)
        assert f"Result posted to board.result.{tid}" in result
        mock_client.publish.assert_called_once()
        # Verify message type is result
        args, kwargs = mock_client.publish.call_args
        assert kwargs["message_type"] == "result"
        assert kwargs["payload"]["output_dir"] == "results/dir"
        assert kwargs["payload"]["exit_code"] == 0

@pytest.mark.asyncio
async def test_post_response_with_message():
    tid = str(ULID())
    with patch("masatools.skills.common.board.get_nats_client", new_callable=AsyncMock) as mock_get_nats:
        mock_client = mock_get_nats.return_value
        
        result = await post_response(message="Operation successful", exit_code=0, thread_id=tid)
        assert f"Result posted to board.result.{tid}" in result
        mock_client.publish.assert_called_once()
        args, kwargs = mock_client.publish.call_args
        assert kwargs["payload"]["message"] == "Operation successful"
        assert "output_dir" not in kwargs["payload"]

@pytest.mark.asyncio
async def test_get_my_profile():
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "agent": {
                    "id": "agent-123",
                    "name": "Test Agent",
                    "role": "worker",
                    "mission": "Be efficient"
                },
                "team_ids": ["team-123"],
                "teams": [
                    {"id": "team-123", "name": "Test Team", "mission": "Save the world"}
                ],
                "team_mission": "Save the world"
            }
        )
        
        from masatools.skills.common.board import get_my_profile
        result = await get_my_profile()
        
        assert "Agent ID: agent-123" in result
        assert "System Role: worker" in result
        assert "Your Contribution Mission: Be efficient" in result
        assert "Teams:" in result
        assert "team-123: Test Team" in result
        assert "Team Mission: Save the world" in result

@pytest.mark.asyncio
async def test_get_team_blueprint():
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "team_id": "team-123",
                "structure_mermaid": "graph TD\n  A --> B",
                "members": [
                    {"id": "agent-a", "name": "Agent A", "role": "manager", "mission": "Lead"},
                    {"id": "agent-b", "name": "Agent B", "role": "worker", "mission": "Work"}
                ]
            }
        )
        
        from masatools.skills.common.board import get_team_blueprint
        result = await get_team_blueprint("team-123")
        
        assert "Team ID: team-123" in result
        assert "graph TD" in result
        assert "Agent A (manager)" in result
        assert "Agent B (worker)" in result

@pytest.mark.asyncio
async def test_get_team_blueprint_uses_single_profile_team():
    context = board.get_default_context()
    previous_thread_id = context.current_thread_id
    context.current_thread_id = None
    profile_response = MagicMock(
        status_code=200,
        json=lambda: {"agent": {"id": "agent-a"}, "team_ids": ["team-123"]},
    )
    blueprint_response = MagicMock(
        status_code=200,
        json=lambda: {
            "team_id": "team-123",
            "structure_mermaid": "graph TD\n  A --> B",
            "members": []
        },
    )

    try:
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = [profile_response, blueprint_response]

            from masatools.skills.common.board import get_team_blueprint
            result = await get_team_blueprint()

            assert "Team ID: team-123" in result
            assert mock_get.call_args_list[0].args[0].endswith("/agents/" + board.get_default_context().agent_id)
            assert mock_get.call_args_list[1].args[0].endswith("/teams/team-123/blueprint")
    finally:
        context.current_thread_id = previous_thread_id

@pytest.mark.asyncio
async def test_get_team_blueprint_uses_active_thread_team_first():
    context = board.get_default_context()
    previous_thread_id = context.current_thread_id
    context.current_thread_id = "thread-123"
    thread_response = MagicMock(status_code=200, json=lambda: {"id": "thread-123", "team_id": "team-thread"})
    blueprint_response = MagicMock(
        status_code=200,
        json=lambda: {
            "team_id": "team-thread",
            "structure_mermaid": "graph TD\n  A --> B",
            "members": []
        },
    )

    try:
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = [thread_response, blueprint_response]

            from masatools.skills.common.board import get_team_blueprint
            result = await get_team_blueprint()

            assert "Team ID: team-thread" in result
            assert mock_get.call_args_list[0].args[0].endswith("/threads/thread-123")
            assert mock_get.call_args_list[1].args[0].endswith("/teams/team-thread/blueprint")
    finally:
        context.current_thread_id = previous_thread_id

@pytest.mark.asyncio
async def test_get_team_blueprint_requires_explicit_team_for_multiple_memberships():
    context = board.get_default_context()
    previous_thread_id = context.current_thread_id
    context.current_thread_id = None
    profile_response = MagicMock(
        status_code=200,
        json=lambda: {"agent": {"id": "agent-a"}, "team_ids": ["team-a", "team-b"]},
    )

    try:
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = profile_response

            from masatools.skills.common.board import get_team_blueprint
            result = await get_team_blueprint()

            assert "team_id is ambiguous" in result
            assert "team-a, team-b" in result
    finally:
        context.current_thread_id = previous_thread_id

@pytest.mark.asyncio
async def test_get_network():
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: [
                {
                    "agent_id": "boss-agent",
                    "relation": {"type": "leader", "category": "vertical"},
                    "status": "online",
                    "mission": "Direct everything"
                }
            ]
        )
        
        from masatools.skills.common.board import get_network
        result = await get_network()
        
        assert "Your Local Network:" in result
        assert "boss-agent (leader/vertical)" in result
        assert "Status:" not in result
        assert "Mission: Direct everything" in result

@pytest.mark.asyncio
async def test_create_thread_success():
    tid = str(ULID())
    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {"thread_id": tid, "input_dir": "tasks/input"}
    
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        
        result = await create_thread("do something", "2026-12-31", team_id="team-a")
        assert f"Thread created: {tid}" in result
        mock_post.assert_called_once()
        # Check payload
        args, kwargs = mock_post.call_args
        assert kwargs["json"]["command"] == "do something"
        assert kwargs["json"]["team_id"] == "team-a"

@pytest.mark.asyncio
async def test_create_subthread_success():
    tid = str(ULID())
    parent_tid = str(ULID())
    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {"thread_id": tid, "input_dir": "tasks/input"}
    
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        
        result = await create_subthread(parent_tid, "do child task")
        assert f"Thread created: {tid}" in result
        mock_post.assert_called_once()
        # Check payload
        args, kwargs = mock_post.call_args
        assert kwargs["json"]["command"] == "do child task"
        assert kwargs["json"]["parent_thread_id"] == parent_tid

@pytest.mark.asyncio
async def test_request_reflection_success():
    req_id = str(ULID())
    ref_tid = str(ULID())
    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {"request_id": req_id, "reflection_thread_id": ref_tid}
    
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        
        result = await request_reflection("parent-thread-123", "2026-12-31")
        assert f"Request ID: {req_id}" in result
        assert f"Reflection Subthread ID: {ref_tid}" in result
        mock_post.assert_called_once()

@pytest.mark.asyncio
async def test_submit_reflection_success():
    ref_id = str(ULID())
    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {"id": ref_id}
    
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        
        result = await submit_reflection("req-123", "target-agent", "clarity", 1, "Good work", "Keep it up")
        assert f"Reflection ID: {ref_id}" in result
        mock_post.assert_called_once()

@pytest.mark.asyncio
async def test_send_offer_success():
    tid = str(ULID())
    with patch("masatools.skills.common.board.get_nats_client", new_callable=AsyncMock) as mock_get_nats:
        mock_client = mock_get_nats.return_value
        
        result = await send_offer(3600, 0.9, thread_id=tid)
        assert f"Offer sent for thread {tid}" in result
        mock_client.publish.assert_called_once()
        args, kwargs = mock_client.publish.call_args
        assert kwargs["message_type"] == "offer"
        assert kwargs["payload"]["eta_seconds"] == 3600

@pytest.mark.asyncio
async def test_send_assign_success():
    tid = str(ULID())
    with patch("masatools.skills.common.board.get_nats_client", new_callable=AsyncMock) as mock_get_nats:
        mock_client = mock_get_nats.return_value
        
        result = await send_assign(["agent-b"], reason="Best candidate", thread_id=tid)
        assert f"Assignment sent to ['agent-b'] for thread {tid}" in result
        mock_client.publish.assert_called_once()
        args, kwargs = mock_client.publish.call_args
        assert kwargs["message_type"] == "assign"
        assert kwargs["to"] == ["agent-b"]

def test_sync_from_s3_path():
    tid = str(ULID())
    with patch("masatools.skills.common.storage.get_s3_client") as mock_get_s3, \
         patch("masatools.skills.common.storage.os.makedirs") as mock_makedirs:
        mock_client = mock_get_s3.return_value
        
        # Test download
        result = sync_from_s3(tid, "input/")
        assert f"tasks/{tid}/input/" in result
        mock_client.download_directory.assert_called_once()
        mock_makedirs.assert_called()

def test_sync_to_s3_upload():
    tid = str(ULID())
    with patch("masatools.skills.common.storage.get_s3_client") as mock_get_s3:
        mock_client = mock_get_s3.return_value
        
        # Mock os.path.exists to return True
        with patch("os.path.exists", return_value=True):
            result = sync_to_s3(tid, "local_file.txt")
            assert "Uploaded 'local_file.txt'" in result
            mock_client.upload_file.assert_called_with(tid, "local_file.txt")
