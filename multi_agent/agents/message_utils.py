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


def with_preferences(text: str, preferences: str | None) -> str:
    """Prefixes a node's LLM input with the user's long-term preferences, when
    any are known for this session. Used instead of a per-agent prompt change
    so every consumer (orchestrator, faq, report) shares one code path."""

    if not preferences:
        return text
    return f"[Preferências de longo prazo do usuário: {preferences}]\n\n{text}"
