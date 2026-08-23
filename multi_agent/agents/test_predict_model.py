import json
from typing import cast
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from multi_agent.entity import AgentName, PredictionItem, State
from multi_agent.agents.predict_model import make_predict_model_func


class TestPredictModelFunc:
    def test_parses_predictions_into_prediction_items(self):
        predict_model_agent = MagicMock()
        predict_model_agent.invoke.return_value = {
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
        }
        predict_model_func = make_predict_model_func(predict_model_agent)

        result = predict_model_func(cast(State, {"current_request": "notebook Dell Latitude 5420"}))

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

    def test_raises_when_the_agent_hallucinates_a_malformed_prediction_shape(self):
        predict_model_agent = MagicMock()
        predict_model_agent.invoke.return_value = {
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
        }
        predict_model_func = make_predict_model_func(predict_model_agent)

        with pytest.raises(ValidationError):
            predict_model_func(cast(State, {"current_request": "notebook Dell Latitude 5420"}))
