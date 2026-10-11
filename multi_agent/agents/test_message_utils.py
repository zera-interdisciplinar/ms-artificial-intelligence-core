import pytest

from multi_agent.exception import AgentOutputException

from multi_agent.agents.message_utils import parse_json_message


def test_parses_fenced_json_split_in_content_blocks():
    content = [{"type": "text", "text": '```json\n{"answer": "ok"'}, {"type": "text", "text": "}\n```"}]
    assert parse_json_message(content, "answer") == {"answer": "ok"}


def test_non_json_output_is_an_agent_output_error():
    with pytest.raises(AgentOutputException, match="not JSON"):
        parse_json_message("desculpe, não entendi")


def test_missing_required_key_is_an_agent_output_error():
    with pytest.raises(AgentOutputException, match="blocked_reason"):
        parse_json_message('{"blocked": false}', "blocked", "blocked_reason")
