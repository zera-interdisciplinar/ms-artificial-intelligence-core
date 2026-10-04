from uuid import uuid4

from _internal.mcp.session import McpSessionStore


def test_expired_session_is_gone():
    store = McpSessionStore(ttl_seconds=0)
    store.put("s", "Bearer t", uuid4(), uuid4())
    # ttl 0 expires immediately; monotonic check uses >=
    assert store.get("s") is None
