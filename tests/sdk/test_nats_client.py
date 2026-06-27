import json

import pytest
from ulid import ULID

from masatools.core.context import AgentContext
from masatools.core.nats_client import NATSClient


class FakeMsg:
    def __init__(self, payload):
        self.data = json.dumps(payload).encode()
        self.acked = False

    async def ack(self):
        self.acked = True


class FakePullSubscription:
    def __init__(self, messages):
        self.messages = messages

    async def fetch(self, count, timeout):
        return self.messages[:count]


class FakeJetStream:
    def __init__(self, messages):
        self.messages = messages

    async def pull_subscribe(self, subject, durable, stream):
        return FakePullSubscription(self.messages)


def make_client(messages):
    context = AgentContext(
        agent_id="agent-b",
        nats_url="nats://localhost:4222",
        api_url="http://localhost/api/v1",
    )
    client = NATSClient(context)
    client.js = FakeJetStream(messages)
    return client


def make_task(to=None, observers=None):
    return {
        "type": "task",
        "thread_id": str(ULID()),
        "from": "agent-a",
        "to": to or [],
        "observers": observers or [],
        "timestamp": 1,
        "payload": {"command": "run"},
    }


def make_result(thread_id=None, from_agent="agent-a", to=None, payload=None):
    return {
        "type": "result",
        "thread_id": thread_id or str(ULID()),
        "from": from_agent,
        "to": to or [],
        "observers": [],
        "timestamp": 1,
        "payload": payload or {"message": "done", "exit_code": 0},
    }


@pytest.mark.asyncio
async def test_pull_task_returns_targeted_task_and_acks():
    msg = FakeMsg(make_task(to=["agent-b"]))
    client = make_client([msg])

    envelope = await client.pull_task(
        stream="board_tasks",
        subject="board.task.*",
        durable="worker-agent-b",
        target_agent_id="agent-b",
    )

    assert envelope is not None
    assert envelope.to == ["agent-b"]
    assert msg.acked is True


@pytest.mark.asyncio
async def test_pull_task_skips_observer_only_task_and_acks():
    msg = FakeMsg(make_task(to=["agent-c"], observers=["agent-b"]))
    client = make_client([msg])

    envelope = await client.pull_task(
        stream="board_tasks",
        subject="board.task.*",
        durable="worker-agent-b",
        target_agent_id="agent-b",
    )

    assert envelope is None
    assert msg.acked is True


@pytest.mark.asyncio
async def test_pull_task_skips_unrelated_task_and_acks():
    msg = FakeMsg(make_task(to=["agent-c"]))
    client = make_client([msg])

    envelope = await client.pull_task(
        stream="board_tasks",
        subject="board.task.*",
        durable="worker-agent-b",
        target_agent_id="agent-b",
    )

    assert envelope is None
    assert msg.acked is True


@pytest.mark.asyncio
async def test_pull_task_scans_batch_until_targeted_task():
    unrelated = FakeMsg(make_task(to=["agent-c"]))
    targeted = FakeMsg(make_task(to=["agent-b"]))
    client = make_client([unrelated, targeted])

    envelope = await client.pull_task(
        stream="board_tasks",
        subject="board.task.*",
        durable="worker-agent-b",
        target_agent_id="agent-b",
        batch_size=10,
    )

    assert envelope is not None
    assert envelope.to == ["agent-b"]
    assert unrelated.acked is True
    assert targeted.acked is True


@pytest.mark.asyncio
async def test_pull_task_buffers_additional_targeted_tasks_from_batch():
    first = FakeMsg(make_task(to=["agent-b"]))
    second = FakeMsg(make_task(to=["agent-b"]))
    client = make_client([first, second])

    first_envelope = await client.pull_task(
        stream="board_tasks",
        subject="board.task.*",
        durable="worker-agent-b",
        target_agent_id="agent-b",
        batch_size=10,
    )
    second_envelope = await client.pull_task(
        stream="board_tasks",
        subject="board.task.*",
        durable="worker-agent-b",
        target_agent_id="agent-b",
        batch_size=10,
    )

    assert first_envelope is not None
    assert second_envelope is not None
    assert first_envelope.thread_id != second_envelope.thread_id
    assert first.acked is True
    assert second.acked is True


@pytest.mark.asyncio
async def test_pull_task_without_target_filter_preserves_legacy_behavior():
    msg = FakeMsg(make_task(to=["agent-c"]))
    client = make_client([msg])

    envelope = await client.pull_task(
        stream="board_tasks",
        subject="board.task.*",
        durable="worker-agent-b",
    )

    assert envelope is not None
    assert envelope.to == ["agent-c"]
    assert msg.acked is True


@pytest.mark.asyncio
async def test_pull_message_returns_filtered_result_and_acks():
    tid = str(ULID())
    unrelated = FakeMsg(make_result(thread_id=tid, from_agent="agent-c", to=["agent-b"]))
    targeted = FakeMsg(make_result(thread_id=tid, from_agent="agent-a", to=["agent-b"], payload={"message": "draft ready"}))
    client = make_client([unrelated, targeted])

    envelope = await client.pull_message(
        stream="board_tasks",
        subject=f"board.result.{tid}",
        durable="wait-result-agent-b",
        target_agent_id="agent-b",
        from_agent="agent-a",
        message_type="result",
        thread_id=tid,
        message_contains="draft ready",
    )

    assert envelope is not None
    assert envelope.thread_id == tid
    assert envelope.from_agent == "agent-a"
    assert unrelated.acked is True
    assert targeted.acked is True


@pytest.mark.asyncio
async def test_pull_message_skips_unaddressed_result():
    tid = str(ULID())
    msg = FakeMsg(make_result(thread_id=tid, from_agent="agent-a", to=["agent-c"]))
    client = make_client([msg])

    envelope = await client.pull_message(
        stream="board_tasks",
        subject=f"board.result.{tid}",
        durable="wait-result-agent-b",
        target_agent_id="agent-b",
        message_type="result",
        thread_id=tid,
    )

    assert envelope is None
    assert msg.acked is True
