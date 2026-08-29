import asyncio
import json
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from multi_agent.entity import AgentName, PredictionItem, State
from multi_agent.agents.predict_model import make_predict_model_func


class TestPredictModelFunc:
    def test_parses_predictions_into_prediction_items(self):
        predict_model_agent = MagicMock()
        predict_model_agent.ainvoke = AsyncMock(return_value={
            "messages": [
                MagicMock(
                    content=json.dumps(
                        {
                            "predictions": [
                                {
                                    "item": "Notebook Dell Latitude 5420",
                                    "estimated_remaining_months": 8,
                                    "adjusted": False,
                                    "adjustment_reason": None,
                                }
                            ]
                        }
                    )
                )
            ]
        })
        predict_model_func = make_predict_model_func(predict_model_agent)

        result = asyncio.run(predict_model_func(cast(State, {"current_request": "notebook Dell Latitude 5420"})))

        assert result == {
            "called_agents": [AgentName.PREDICT_MODEL],
            "predictions": [
                PredictionItem(
                    item="Notebook Dell Latitude 5420",
                    estimated_remaining_months=8,
                    adjusted=False,
                    adjustment_reason=None,
                )
            ],
        }

    def test_parses_a_null_estimate_for_an_item_the_agent_marked_ineligible(self):
        predict_model_agent = MagicMock()
        predict_model_agent.ainvoke = AsyncMock(return_value={
            "messages": [
                MagicMock(
                    content=json.dumps(
                        {
                            "predictions": [
                                {
                                    "item": "Tablet Apple iPad",
                                    "estimated_remaining_months": None,
                                    "adjusted": False,
                                    "adjustment_reason": "climateZone não informado",
                                }
                            ]
                        }
                    )
                )
            ]
        })
        predict_model_func = make_predict_model_func(predict_model_agent)

        result = asyncio.run(predict_model_func(cast(State, {"current_request": "tablet Apple iPad"})))

        assert result["predictions"] == [
            PredictionItem(
                item="Tablet Apple iPad",
                estimated_remaining_months=None,
                adjusted=False,
                adjustment_reason="climateZone não informado",
            )
        ]

    def test_raises_when_the_agent_hallucinates_a_malformed_prediction_shape(self):
        predict_model_agent = MagicMock()
        predict_model_agent.ainvoke = AsyncMock(return_value={
            "messages": [
                MagicMock(
                    content=json.dumps(
                        {
                            "predictions": [
                                {
                                    "item": "Notebook Dell Latitude 5420",
                                    "estimated_remaining_months": "oito meses",
                                    "adjusted": False,
                                    "adjustment_reason": None,
                                }
                            ]
                        }
                    )
                )
            ]
        })
        predict_model_func = make_predict_model_func(predict_model_agent)

        with pytest.raises(ValidationError):
            asyncio.run(predict_model_func(cast(State, {"current_request": "notebook Dell Latitude 5420"})))
