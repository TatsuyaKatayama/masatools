import json
import time
from typing import Optional, List, Callable, Awaitable
import nats
from nats.errors import TimeoutError
from .models import MessageEnvelope
from .context import AgentContext

class NATSClient:
    def __init__(self, context: AgentContext):
        self.context = context
        self.nc = None
        self.js = None

    async def connect(self):
        opts = {
            "servers": [self.context.nats_url],
            "name": self.context.agent_id,
        }
        
        if self.context.nats_jwt and self.context.nats_nkey:
            # Note: nats-py expects a cb for user_credentials or user_jwt
            # This is a simplified placeholder for JWT/NKey auth
            pass

        self.nc = await nats.connect(**opts)
        self.js = self.nc.jetstream()

    async def publish(self, subject: str, message_type: str, payload: dict, thread_id: str, to: List[str] = []):
        envelope = MessageEnvelope(
            type=message_type,
            thread_id=thread_id,
            from_agent=self.context.agent_id,
            to=to,
            timestamp=int(time.time()),
            payload=payload
        )
        data = envelope.model_dump_json(by_alias=True).encode()
        await self.js.publish(subject, data)

    async def pull_task(self, stream: str, subject: str, durable: str) -> Optional[MessageEnvelope]:
        try:
            psub = await self.js.pull_subscribe(subject, durable, stream=stream)
            msgs = await psub.fetch(1, timeout=1)
            for msg in msgs:
                data = json.loads(msg.data.decode())
                envelope = MessageEnvelope(**data)
                await msg.ack()
                return envelope
        except TimeoutError:
            return None
        except Exception as e:
            print(f"Error pulling task: {e}")
            return None

    async def close(self):
        if self.nc:
            await self.nc.drain()
