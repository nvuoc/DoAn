"""NLU span validator, anti-injection guard, and semantic proposal verification."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from src.conversation.errors import ErrorCode, ConversationCoreException


# Patterns representing prompt injection or pseudo control-plane instructions in user utterances
INJECTION_PATTERNS = [
    re.compile(r"^\s*system\s*:", re.IGNORECASE),
    re.compile(r"bỏ\s+qua\s+(?:mọi\s+)?(?:hướng\s+dẫn|xác\s+nhận|chính\s+sách|quy\s+tắc)", re.IGNORECASE),
    re.compile(r"hãy\s+đóng\s+vai\s+(?:hệ\s+thống|admin|tổng\s+đài|root)", re.IGNORECASE),
    re.compile(r"^\s*\{\s*[\"']kind[\"']\s*:\s*[\"'](?:ownership_changed|delivery)[\"']", re.IGNORECASE),
]


def check_anti_injection(text: str) -> bool:
    """Returns True if suspicious injection pattern detected, False otherwise."""
    for pat in INJECTION_PATTERNS:
        if pat.search(text):
            return True
    return False


def sanitize_utterance(text: str) -> str:
    """Ensure user text is treated purely as content and cannot alter privileged control state."""
    # Strip any leading 'system:' or emulate tokens
    sanitized = re.sub(r"^\s*system\s*:\s*", "", text, flags=re.IGNORECASE)
    return sanitized.strip()


def validate_span(original_text: str, start: int, end: int, expected_text: Optional[str] = None) -> bool:
    """Validate that Unicode code points [start, end) fall within bounds and match expected string."""
    if start < 0 or end > len(original_text) or start > end:
        return False
    actual_span = original_text[start:end]
    if expected_text is not None and actual_span != expected_text:
        return False
    return True
