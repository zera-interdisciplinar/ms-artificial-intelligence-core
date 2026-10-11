import asyncio
from unittest.mock import patch

from langgraph.checkpoint.redis import RedisSaver

from .async_redis_saver import AsyncRedisSaver


def test_async_saver_delegates_to_the_sync_api():
    saver = AsyncRedisSaver.__new__(AsyncRedisSaver)
    config = {"configurable": {"thread_id": "t"}}

    with (
        patch.object(RedisSaver, "get_tuple", return_value="tuple") as get_tuple,
        patch.object(RedisSaver, "put", return_value=config) as put,
        patch.object(RedisSaver, "put_writes") as put_writes,
        patch.object(RedisSaver, "list", return_value=iter(["a"])) as list_checkpoints,
    ):
        assert asyncio.run(saver.aget_tuple(config)) == "tuple"
        assert asyncio.run(saver.aput(config, {}, {}, {})) == config
        asyncio.run(saver.aput_writes(config, [], "task"))

        async def _collect():
            return [item async for item in saver.alist(config)]

        assert asyncio.run(_collect()) == ["a"]

    get_tuple.assert_called_once_with(saver, config)
    put.assert_called_once()
    put_writes.assert_called_once()
    list_checkpoints.assert_called_once()
