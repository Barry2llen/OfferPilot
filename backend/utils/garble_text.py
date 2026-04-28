import re
import unicodedata
from dataclasses import dataclass


# 常见“可读”字符范围：中文、英文、数字、常见中英文标点
RE_CJK = re.compile(r'[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]')
RE_ASCII_WORD = re.compile(r'[A-Za-z0-9]')
RE_COMMON_PUNC = re.compile(
    r"""[.,;:!?'"()\[\]{}<>\-_/\\@#$%^&*+=|~`，。；：！？、“”‘’（）《》【】—…·]"""
)

# 典型 mojibake 片段（只作加分项，不作为主判据）
RE_MOJIBAKE = re.compile(r'(Ã.|Â.|â.|ð.|�)')


@dataclass
class GarbleResult:
    is_garbled: bool
    score: float
    reasons: dict


def _is_private_use(ch: str) -> bool:
    cp = ord(ch)
    return (
        0xE000 <= cp <= 0xF8FF or
        0xF0000 <= cp <= 0xFFFFD or
        0x100000 <= cp <= 0x10FFFD
    )


def _is_readable_char(ch: str) -> bool:
    if ch.isspace():
        return True
    return bool(
        RE_CJK.match(ch) or
        RE_ASCII_WORD.match(ch) or
        RE_COMMON_PUNC.match(ch)
    )


def detect_garbled_text(text: str, *, min_len: int = 20, threshold: float = 0.35) -> GarbleResult:
    """
    返回是否疑似乱码，以及一个 0~1 左右的评分。
    分数越高，越像乱码。
    """
    if not text:
        return GarbleResult(True, 1.0, {"empty_text": 1.0})

    # 去掉首尾空白，减少噪音
    text = text.strip()
    if not text:
        return GarbleResult(True, 1.0, {"blank_text": 1.0})

    total = len(text)
    non_ws = [c for c in text if not c.isspace()]
    n = max(len(non_ws), 1)

    replacement = sum(c == "\uFFFD" for c in non_ws) / n

    control = 0
    private_use = 0
    unreadable = 0

    for c in non_ws:
        cat = unicodedata.category(c)
        if cat in {"Cc", "Cs"}:   # 控制字符、代理项
            control += 1
        elif _is_private_use(c) or cat in {"Co", "Cn"}:  # 私有区、未分配
            private_use += 1

        if not _is_readable_char(c):
            unreadable += 1

    control_ratio = control / n
    private_ratio = private_use / n
    unreadable_ratio = unreadable / n

    mojibake_hits = len(RE_MOJIBAKE.findall(text))
    mojibake_ratio = mojibake_hits / max(total, 1)

    # 文本极短时，更容易误判，所以只做轻微加权
    short_penalty = 0.15 if total < min_len else 0.0

    # 综合评分：你可以按数据集再调
    score = (
        replacement * 0.45 +
        control_ratio * 0.20 +
        private_ratio * 0.20 +
        unreadable_ratio * 0.35 +
        mojibake_ratio * 0.15 +
        short_penalty
    )

    reasons = {
        "replacement_ratio": round(replacement, 4),
        "control_ratio": round(control_ratio, 4),
        "private_ratio": round(private_ratio, 4),
        "unreadable_ratio": round(unreadable_ratio, 4),
        "mojibake_ratio": round(mojibake_ratio, 4),
        "length": total,
        "score": round(score, 4),
    }

    return GarbleResult(score >= threshold, score, reasons)