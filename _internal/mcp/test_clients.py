import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from _internal.mcp.clients import fetch_ms_inventory_tools, fetch_predict_model_context


def _tool(name: str, result=None) -> MagicMock:
    tool = MagicMock(name=name)
    tool.name = name
    tool.ainvoke = AsyncMock(return_value=result)
    return tool


def _envs() -> MagicMock:
    envs = MagicMock()
    envs.PREDICT_MODEL_MCP_URL = "https://gateway.zera.internal/predictor"
    envs.PREDICT_MODEL_API_KEY = "predict-key"
    envs.MS_INVENTORY_MCP_URL = "https://gateway.zera.internal/inventory"
    envs.MS_INVENTORY_API_KEY = "inventory-key"
    return envs


@patch("_internal.mcp.clients.MultiServerMCPClient")
def test_predict_context_sends_the_apikey_and_splits_the_vocabularies(mock_client):
    batch = _tool("predict_time_to_failure_batch")
    mock_client.return_value.get_tools = AsyncMock(return_value=[
        batch,
        _tool("list_valid_categories", ["notebook", "celular"]),
        _tool("list_valid_climate_zones", ["TROPICAL", "ARID"]),
    ])

    tool, categories, climate_zones = asyncio.run(fetch_predict_model_context(_envs()))

    mock_client.assert_called_once_with({
        "predict_model": {
            "url": "https://gateway.zera.internal/predictor",
            "transport": "streamable_http",
            "headers": {"apikey": "predict-key"},
        }
    })
    assert tool is batch
    assert categories == ["notebook", "celular"]
    assert climate_zones == ["TROPICAL", "ARID"]


@patch("_internal.mcp.clients.MultiServerMCPClient")
def test_predict_context_fails_loudly_when_a_tool_is_missing(mock_client):
    mock_client.return_value.get_tools = AsyncMock(return_value=[_tool("predict_time_to_failure_batch")])

    with pytest.raises(AssertionError, match="list_valid_categories"):
        asyncio.run(fetch_predict_model_context(_envs()))


@patch("_internal.mcp.clients.MultiServerMCPClient")
def test_inventory_tools_require_get_disposal_report(mock_client):
    mock_client.return_value.get_tools = AsyncMock(return_value=[_tool("get_inventory")])

    with pytest.raises(AssertionError, match="get_disposal_report"):
        asyncio.run(fetch_ms_inventory_tools(_envs()))

    report = _tool("get_disposal_report")
    mock_client.return_value.get_tools = AsyncMock(return_value=[report])
    assert asyncio.run(fetch_ms_inventory_tools(_envs())) == [report]
