"""Helpers to normalize LLM message content before JSON parsing.

When a model is bound to tools, some providers (e.g. Gemini) return message
content as a list of content blocks (e.g. [{"type": "text", "text": "..."}])
instead of a plain string, even for the final answer. These helpers extract
the plain text so callers can safely json.loads() it regardless of provider.
"""

import json
import re
from typing import Any

_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def extract_text(content: Any) -> str:
    """Normalizes a message's content field into a plain text string."""

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        return "".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )

    return str(content)


def parse_json_message(content: Any) -> Any:
    """Extracts plain text from message content and parses it as JSON."""

    text = _CODE_FENCE_RE.sub("", extract_text(content)).strip()
    return json.loads(text)
