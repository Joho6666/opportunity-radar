"""Natural-language Listener (openmagpie-style watch), compiled once per radar.

A radar may carry a listener_description like「寻找正在抱怨短视频制作太慢、
希望自动批量生产视频的商家」. compile() turns it into concrete gates:
positive/negative keyword signals, query suggestions and exclusion rules.
LLM compilation when configured; deterministic keyword split otherwise (so the
feature works with zero LLM and in tests).

Application (run time): an item matching ANY negative signal and NO positive
signal is gated out before the expensive LLM call; items matching positive
signals get a small personal-fit boost in MoneyScore.
"""

import logging
import re

from ..core.config import get_settings
from ..schemas.domain import RadarCreate, RadarRead
from ..schemas.intelligence import RadarListenerConfig

logger = logging.getLogger(__name__)


_CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")
_ASCII_TOKEN = re.compile(r"[A-Za-z0-9_]{2,}")


def _tokens(text: str) -> list[str]:
    """CJK char-bigrams + ASCII words: whole Chinese sentences are useless as
    substring-matching terms, bigrams hit reliably."""
    text = text or ""
    tokens: list[str] = []
    for word in _ASCII_TOKEN.findall(text.lower()):
        tokens.append(word)
    for run in _CJK_RUN.findall(text):
        if len(run) == 1:
            tokens.append(run)
            continue
        tokens.extend(run[i : i + 2] for i in range(len(run) - 1))
    return tokens[:16]


def rule_compile(description: str) -> RadarListenerConfig:
    """Deterministic fallback: split description into keyword-ish phrases.
    Sentences containing complaint/need markers go to positive; explicit
    negations (不是/排除/不要/不含) go to negative."""
    positive: list[str] = []
    negative: list[str] = []
    markers = ("抱怨", "求", "想要", "需要", "希望", "付费", "有偿", "预算", "痛点", "难用", "太慢", "太贵")
    negation_markers = ("不是", "排除", "不要", "不含", "忽略")
    for clause in re.split(r"[，。；;,\n]", description):
        clause = clause.strip()
        if not clause:
            continue
        negated = any(marker in clause for marker in negation_markers)
        if negated:
            clause = clause
            for marker in negation_markers:
                clause = clause.replace(marker, "")
            negative.extend(_tokens(clause)[:4])
            continue
        keywords = _tokens(clause)[:4]
        if any(marker in clause for marker in markers):
            positive.extend(keywords)
        else:
            positive.extend(keywords[:2])
    queries = [f"{' '.join(positive[:3])} 有偿"] if positive else []
    return RadarListenerConfig(positive_signals=list(dict.fromkeys(positive))[:12], negative_signals=list(dict.fromkeys(negative))[:12], search_queries=queries, exclusion_rules=[])


async def compile_listener(radar: RadarCreate) -> RadarListenerConfig:
    from .ai_service import compile_listener_llm

    compiled = await compile_listener_llm(radar.listener_description)
    if compiled is not None:
        return compiled
    return rule_compile(radar.listener_description)


def listener_matches(item_text: str, config: RadarListenerConfig | None) -> tuple[bool, int]:
    """Returns (passes_listener, positive_hits). Missing config always passes.

    Semantics (openmagpie-style semantic_filter): an item must match the
    listener's positive signals and avoid its negative/exclusion rules — an
    item that matches nothing is NOT for this radar."""
    if config is None:
        return True, 0
    text = (item_text or "").lower()
    positive_hits = sum(1 for term in config.positive_signals if term and term.lower() in text)
    negative_hits = sum(1 for term in config.negative_signals if term and term.lower() in text)
    if any(rule and rule.lower() in text for rule in config.exclusion_rules):
        return False, positive_hits
    if negative_hits > 0:
        return False, positive_hits
    if config.positive_signals and positive_hits == 0:
        return False, 0
    return True, positive_hits


def listener_boost(positive_hits: int) -> int:
    """personal-fit points added in MoneyScore inputs, capped."""
    return min(10, positive_hits * 5)


def config_for_radar(radar: RadarRead) -> RadarListenerConfig | None:
    if not getattr(radar, "listener_description", ""):
        return None
    if radar.listener_config:
        try:
            return RadarListenerConfig.model_validate(radar.listener_config)
        except Exception:
            logger.warning("invalid listener_config on radar", extra={"radar_id": radar.id})
    return rule_compile(radar.listener_description)


def provider_available() -> bool:
    settings = get_settings()
    return bool(settings.llm_api_key and settings.llm_base_url)
