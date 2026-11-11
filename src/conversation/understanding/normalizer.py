"""Vietnamese spoken number, time, and address normalizer.

Enforces:
- Spoken digit sequence to Arabic numbers ("một ba hai" -> "132")
- Compound Vietnamese numbers ("hai mốt" -> "21", "năm mươi tư" -> "54", "hai lăm" -> "25")
- Slash/fraction for house numbers ("một hai ba xuyệt bốn" -> "123/4")
- Spoken passenger capacity ("chục người" -> 10)
- Relative time anchored against received_at with Asia/Ho_Chi_Minh
"""
from __future__ import annotations

from datetime import datetime, timedelta
import re
from typing import Dict, List, Optional, Tuple
try:
    from zoneinfo import ZoneInfo
    TZ_VN = ZoneInfo("Asia/Ho_Chi_Minh")
except Exception:
    from datetime import timezone
    TZ_VN = timezone(timedelta(hours=7))

# Single digits
DIGIT_MAP = {
    "không": "0",
    "một": "1",
    "hai": "2",
    "ba": "3",
    "bốn": "4",
    "năm": "5",
    "sáu": "6",
    "bảy": "7",
    "bẩy": "7",
    "tám": "8",
    "chín": "9",
}

# Compound numbers dictionary
TEENS_TENS = {
    "mười một": 11,
    "mười hai": 12,
    "mười ba": 13,
    "mười bốn": 14,
    "mười lăm": 15,
    "mười sáu": 16,
    "mười bảy": 17,
    "mười bẩy": 17,
    "mười tám": 18,
    "mười chín": 19,
    "mười": 10,
    "hai mươi mốt": 21,
    "hai mươi lăm": 25,
    "hai mươi nhăm": 25,
    "hai mươi tư": 24,
    "hai mươi": 20,
    "hai mốt": 21,
    "hai lăm": 25,
    "hai nhăm": 25,
    "hai tư": 24,
    "ba mươi mốt": 31,
    "ba mươi lăm": 35,
    "ba mươi tư": 34,
    "ba mươi": 30,
    "ba mốt": 31,
    "ba lăm": 35,
    "ba tư": 34,
    "bốn mươi mốt": 41,
    "bốn mươi lăm": 45,
    "bốn mươi tư": 44,
    "bốn mươi": 40,
    "bốn mốt": 41,
    "bốn lăm": 45,
    "bốn tư": 44,
    "năm mươi mốt": 51,
    "năm mươi lăm": 55,
    "năm mươi tư": 54,
    "năm mươi": 50,
    "năm mốt": 51,
    "năm lăm": 55,
    "năm tư": 54,
    "sáu mươi mốt": 61,
    "sáu mươi lăm": 65,
    "sáu mươi tư": 64,
    "sáu mươi": 60,
    "sáu mốt": 61,
    "sáu lăm": 65,
    "sáu tư": 64,
    "bảy mươi mốt": 71,
    "bảy mươi lăm": 75,
    "bảy mươi tư": 74,
    "bảy mươi": 70,
    "bảy mốt": 71,
    "bảy lăm": 75,
    "bảy tư": 74,
    "tám mươi mốt": 81,
    "tám mươi lăm": 85,
    "tám mươi tư": 84,
    "tám mươi": 80,
    "tám mốt": 81,
    "tám lăm": 85,
    "tám tư": 84,
    "chín mươi mốt": 91,
    "chín mươi lăm": 95,
    "chín mươi tư": 94,
    "chín mươi": 90,
    "chín mốt": 91,
    "chín lăm": 95,
    "chín tư": 94,
}


def normalize_spoken_digits(text: str) -> str:
    """Normalize spoken digit sequences like 'ngõ một ba hai' -> 'ngõ 132'."""
    tokens = text.split()
    result = []
    i = 0
    digit_words = set(DIGIT_MAP.keys())

    while i < len(tokens):
        token_lower = tokens[i].lower()
        if token_lower in digit_words:
            # Gather consecutive digits
            digit_seq = []
            while i < len(tokens) and tokens[i].lower() in digit_words:
                digit_seq.append(DIGIT_MAP[tokens[i].lower()])
                i += 1
            result.append("".join(digit_seq))
        else:
            result.append(tokens[i])
            i += 1
    return " ".join(result)


def normalize_vietnamese_numbers(text: str) -> str:
    """Normalize spoken compound numbers and phrases in address/intent context."""
    norm = text

    # Common spoken compound numbers (longer phrases first)
    for phrase, val in sorted(TEENS_TENS.items(), key=lambda x: len(x[0]), reverse=True):
        pattern = re.compile(rf"\b{re.escape(phrase)}\b", re.IGNORECASE)
        norm = pattern.sub(str(val), norm)

    # Normalize digit sequences (e.g. "một ba hai" -> "132", "một hai ba" -> "123")
    norm = normalize_spoken_digits(norm)

    # Slash numbers: "123 xuyệt 4" -> "123/4"
    slash_pattern = re.compile(
        r"(\b\d+)\s*(?:xuyệt|suyệt|gạch)\s*(\b\d+)",
        re.IGNORECASE,
    )
    norm = slash_pattern.sub(r"\1/\2", norm)

    # Normalize capacity
    norm = re.sub(r"\bchục\s+người\b", "10 người", norm, flags=re.IGNORECASE)
    norm = re.sub(r"\bmột\s+chục\b", "10", norm, flags=re.IGNORECASE)

    return norm


def parse_relative_time(
    phrase: str, anchor_iso: str
) -> Optional[datetime]:
    """Parse relative time anchored against anchor_iso with Asia/Ho_Chi_Minh."""
    try:
        if anchor_iso.endswith("Z"):
            anchor_dt = datetime.fromisoformat(anchor_iso.replace("Z", "+00:00")).astimezone(TZ_VN)
        else:
            anchor_dt = datetime.fromisoformat(anchor_iso).astimezone(TZ_VN)
    except Exception:
        anchor_dt = datetime.now(TZ_VN)

    phrase_lower = phrase.lower().strip()

    # "... phút nữa"
    m_min = re.search(r"(\d+)\s+phút\s+nữa", phrase_lower)
    if m_min:
        mins = int(m_min.group(1))
        return anchor_dt + timedelta(minutes=mins)

    # "nửa tiếng nữa" / "ba mươi phút nữa"
    if "nửa tiếng nữa" in phrase_lower or "30 phút nữa" in phrase_lower:
        return anchor_dt + timedelta(minutes=30)

    # "... tiếng nữa" / "... giờ nữa"
    m_hour = re.search(r"(\d+)\s+(?:tiếng|giờ)\s+nữa", phrase_lower)
    if m_hour:
        hrs = int(m_hour.group(1))
        return anchor_dt + timedelta(hours=hrs)

    # "bảy rưỡi" (default to next 7:30 morning or evening depending on anchor)
    if "bảy rưỡi" in phrase_lower or "7 rưỡi" in phrase_lower or "7h30" in phrase_lower:
        target = anchor_dt.replace(hour=7, minute=30, second=0, microsecond=0)
        if target <= anchor_dt:
            # 19:30 or tomorrow
            target = anchor_dt.replace(hour=19, minute=30, second=0, microsecond=0)
            if target <= anchor_dt:
                target = target + timedelta(days=1)
        return target

    # "sáng mai"
    if "sáng mai" in phrase_lower:
        tomorrow = anchor_dt + timedelta(days=1)
        return tomorrow.replace(hour=8, minute=0, second=0, microsecond=0)

    return None
