import re
import httpx
from typing import List, Tuple, Optional, Set, Dict, Any
from .context import AgentContext

MENTION_REGEX = re.compile(r'@([a-zA-Z0-9_-]+)')

async def resolve_mentions(
    message: str, 
    thread_id: Optional[str], 
    context: AgentContext
) -> Tuple[List[str], Optional[str]]:
    """
    Extracts and resolves mentions from a message.
    Supported: @agent-id, @team
    
    Returns:
        (to_agents, error_code)
    """
    mentions = set(MENTION_REGEX.findall(message))
    if not mentions:
        return [], "NO_RECIPIENT"

    resolved_ids: Set[str] = set()
    has_team_mention = "team" in mentions
    other_mentions = mentions - {"team"}
    
    async with httpx.AsyncClient() as client:
        # 1. Resolve @team if present
        if has_team_mention:
            if not thread_id:
                return [], "TEAM_CONTEXT_REQUIRED"
            
            # Find team_id for the thread
            team_id = None
            try:
                # Use specific thread endpoint
                resp = await client.get(f"{context.api_url}/threads/{thread_id}")
                if resp.status_code == 200:
                    thread_data = resp.json()
                    team_id = thread_data.get("team_id")
            except Exception:
                pass
            
            if not team_id:
                return [], "TEAM_CONTEXT_REQUIRED"
            
            # Fetch team members
            try:
                resp = await client.get(f"{context.api_url}/teams/{team_id}/agents")
                if resp.status_code == 200:
                    members = resp.json()
                    for member in members:
                        aid = member.get("id")
                        if aid and aid != context.agent_id:
                            resolved_ids.add(aid)
                else:
                    return [], "TEAM_CONTEXT_REQUIRED"
            except Exception:
                return [], "TEAM_CONTEXT_REQUIRED"

        # 2. Resolve other @agent-id mentions
        if other_mentions:
            # To be efficient, we could fetch all agents and check existence
            # or fetch each one if there are few. Let's fetch all agents if > 2 mentions.
            if len(other_mentions) > 2:
                try:
                    resp = await client.get(f"{context.api_url}/agents")
                    if resp.status_code == 200:
                        all_agents = {a.get("id") for a in resp.json()}
                        for m in other_mentions:
                            if m in all_agents:
                                if m != context.agent_id:
                                    resolved_ids.add(m)
                            else:
                                return [], "UNKNOWN_MENTION"
                    else:
                        return [], "UNKNOWN_MENTION"
                except Exception:
                    return [], "UNKNOWN_MENTION"
            else:
                for m in other_mentions:
                    try:
                        resp = await client.get(f"{context.api_url}/agents/{m}")
                        if resp.status_code == 200:
                            if m != context.agent_id:
                                resolved_ids.add(m)
                        else:
                            return [], "UNKNOWN_MENTION"
                    except Exception:
                        return [], "UNKNOWN_MENTION"

    if not resolved_ids:
        # This could happen if you only mention yourself and @team is empty
        if has_team_mention and not resolved_ids:
             # If @team was used but resulted in no other members
             return [], "NO_TEAM_MEMBERS"
        return [], "NO_RECIPIENT"

    return sorted(list(resolved_ids)), None
