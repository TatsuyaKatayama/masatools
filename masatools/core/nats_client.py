import json
import time
from typing import Optional, List, Callable, Awaitable
import nats
import nkeys
from nats.errors import TimeoutError
from .models import MessageEnvelope
from .context import AgentContext

class NATSClient:
    def __init__(self, context: AgentContext):
        self.context = context
        self.nc = None
        self.js = None
        self._pull_subscriptions = {}
        self._pending_tasks = {}

    async def connect(self, max_reconnect_attempts: int = 3, connect_timeout: int = 5, allow_reconnect: bool = True):
        import asyncio
        opts = {
            "servers": [self.context.nats_url],
            "name": self.context.agent_id,
            "max_reconnect_attempts": max_reconnect_attempts,
            "connect_timeout": connect_timeout,
            "allow_reconnect": allow_reconnect,
            "dont_randomize": True,
        }
        
        if self.context.nats_jwt and self.context.nats_nkey:
            sk = nkeys.from_seed(self.context.nats_nkey.encode())
            
            async def signature_cb(nonce):
                return sk.sign(nonce)
            
            opts["user_jwt"] = self.context.nats_jwt
            opts["signature_cb"] = signature_cb

        # Use wait_for to ensure we don't hang during initial connection
        self.nc = await asyncio.wait_for(nats.connect(**opts), timeout=connect_timeout + 1)
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
        
        # Signing
        if self.context.nats_nkey:
            import base64
            # We must match the Go server's JSON marshal behavior for verification.
            # Go standard library's json.Marshal sorts map keys, but struct fields follow their definition order.
            # Here we produce a canonical JSON (no whitespace, sorted keys) to be safe.
            # Note: The Go server must also use a consistent method to verify.
            envelope.signature = None
            data_to_sign = json.dumps(envelope.model_dump(by_alias=True, exclude={'signature'}), separators=(',', ':'), sort_keys=True).encode()
            
            sk = nkeys.from_seed(self.context.nats_nkey.encode())
            sig_bytes = sk.sign(data_to_sign)
            envelope.signature = base64.b64encode(sig_bytes).decode()

        data = envelope.model_dump_json(by_alias=True, exclude_none=True).encode()
        await self.js.publish(subject, data)

    async def pull_task(
        self,
        stream: str,
        subject: str,
        durable: str,
        target_agent_id: Optional[str] = None,
        batch_size: int = 100,
    ) -> Optional[MessageEnvelope]:
        try:
            subscription_key = (stream, subject, durable)
            pending = self._pending_tasks.get(subscription_key)
            if pending:
                return pending.pop(0)

            psub = self._pull_subscriptions.get(subscription_key)
            if psub is None:
                psub = await self.js.pull_subscribe(subject, durable, stream=stream)
                self._pull_subscriptions[subscription_key] = psub
            msgs = await psub.fetch(batch_size, timeout=1)
            for msg in msgs:
                data = json.loads(msg.data.decode())
                envelope = MessageEnvelope(**data)
                if target_agent_id is not None and target_agent_id not in envelope.to:
                    await msg.ack()
                    continue
                await msg.ack()
                self._pending_tasks.setdefault(subscription_key, []).append(envelope)

            pending = self._pending_tasks.get(subscription_key)
            if pending:
                return pending.pop(0)
        except TimeoutError:
            return None
        except Exception as e:
            print(f"Error pulling task: {e}")
            return None

    async def close(self):
        if self.nc:
            await self.nc.drain()
