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

    async def connect(self):
        opts = {
            "servers": [self.context.nats_url],
            "name": self.context.agent_id,
        }
        
        if self.context.nats_jwt and self.context.nats_nkey:
            sk = nkeys.from_seed(self.context.nats_nkey.encode())
            
            async def signature_cb(nonce):
                return sk.sign(nonce)
            
            opts["user_jwt"] = self.context.nats_jwt
            opts["signature_cb"] = signature_cb

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
