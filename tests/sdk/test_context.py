import os
from masatools.core.context import get_default_context, AgentContext
import masatools.core.context

def test_agent_context_aws_env_vars(monkeypatch):
    # Clear any existing env vars
    monkeypatch.delenv("S3_ACCESS_KEY", raising=False)
    monkeypatch.delenv("S3_SECRET_KEY", raising=False)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "env-aws-access")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "env-aws-secret")
    
    # Force reset the global context for testing
    masatools.core.context._default_context = None
    
    ctx = get_default_context()
    assert ctx.s3_access_key == "env-aws-access"
    assert ctx.s3_secret_key == "env-aws-secret"

def test_agent_context_s3_key_precedence(monkeypatch):
    # S3_ACCESS_KEY should take precedence over AWS_ACCESS_KEY_ID
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "aws-id")
    monkeypatch.setenv("S3_ACCESS_KEY", "s3-id")
    
    masatools.core.context._default_context = None
    
    ctx = get_default_context()
    assert ctx.s3_access_key == "s3-id"
