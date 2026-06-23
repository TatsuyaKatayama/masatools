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
