"""
Outbound MCP adapters: discover the tools other repositories expose through the
Kong gateway. Every route requires the api-key-auth plugin, so the service key
goes as an apikey header. The core only receives the resulting BaseTools.
"""

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from config.environments import Environments


async def _fetch_tools(
    name: str, url: str | None, api_key: str | None, required: frozenset[str] = frozenset()
) -> list[BaseTool]:
    assert url is not None, f"{name} MCP url must be set"
    assert api_key is not None, f"{name} MCP api key must be set"

    client = MultiServerMCPClient(
        {name: {"url": url, "transport": "streamable_http", "headers": {"apikey": api_key}}}
    )
    tools: list[BaseTool] = await client.get_tools()

    names = [tool.name for tool in tools]
    missing = required - set(names)
    assert not missing, f"{name} MCP is missing required tools {sorted(missing)} (got: {names})"
    return tools


async def fetch_predict_model_context(envs: Environments) -> tuple[BaseTool, list[str], list[str]]:
    """
    Returns predict_time_to_failure_batch plus the valid category/climateZone
    vocabularies, read from the trained model itself (list_valid_categories /
    list_valid_climate_zones) instead of a hand-copied list in the prompt that can
    silently drift from it (see docs/integration-predict-time-to-failure.md).
    """
    tools = {tool.name: tool for tool in await _fetch_tools(
        "predict_model", envs.PREDICT_MODEL_MCP_URL, envs.PREDICT_MODEL_API_KEY,
        required=frozenset({"list_valid_categories", "list_valid_climate_zones", "predict_time_to_failure_batch"}),
    )}

    categories: list[str] = await tools["list_valid_categories"].ainvoke({})
    climate_zones: list[str] = await tools["list_valid_climate_zones"].ainvoke({})
    return tools["predict_time_to_failure_batch"], categories, climate_zones


async def fetch_ms_inventory_tools(envs: Environments) -> list[BaseTool]:
    """Every ms-inventory tool; get_disposal_report must be among them."""
    return await _fetch_tools(
        "ms_inventory", envs.MS_INVENTORY_MCP_URL, envs.MS_INVENTORY_API_KEY,
        required=frozenset({"get_disposal_report"}),
    )
