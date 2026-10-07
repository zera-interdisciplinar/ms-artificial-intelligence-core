import asyncio

from langgraph.checkpoint.redis import RedisSaver


class AsyncRedisSaver(RedisSaver):
    """RedisSaver only implements the sync checkpoint API. ainvoke calls the async
    methods, and BaseCheckpointSaver raises NotImplementedError for them."""

    async def aget_tuple(self, config):
        return await asyncio.to_thread(RedisSaver.get_tuple, self, config)

    async def aput(self, config, checkpoint, metadata, new_versions):
        return await asyncio.to_thread(
            RedisSaver.put, self, config, checkpoint, metadata, new_versions
        )

    async def aput_writes(self, config, writes, task_id, task_path=""):
        return await asyncio.to_thread(
            RedisSaver.put_writes, self, config, writes, task_id, task_path
        )

    async def alist(self, config, *, filter=None, before=None, limit=None):
        items = await asyncio.to_thread(
            lambda: list(RedisSaver.list(self, config, filter=filter, before=before, limit=limit))
        )
        for item in items:
            yield item
