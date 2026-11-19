"""口播事实边界。推测、未批准资料和夸大表述不能进入成片文案。"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, List, Optional


class ClaimLevel(str, Enum):
    CONFIRMED = "confirmed"
    SOURCE_CLAIM = "source_claim"
    INFERENCE = "inference"
    UNKNOWN = "unknown"


@dataclass
class Fact:
    fact_id: str
    text: str
    level: ClaimLevel
    kind: str
    approved: bool = False
    source: str = ""


@dataclass
class CopyDecision:
    accepted: List[str] = field(default_factory=list)
    rejected: List[str] = field(default_factory=list)


# 这些说法比可见事实更强。只有来源原文里已经有同样的词，才可能保留；
# 效果段仍然必须有拍到结果的素材。
EXAGGERATION_MARKERS = (
    "一次清除",
    "一次搞定",
    "立即消失",
    "立刻干净",
    "秒杀",
    "最强",
    "100%",
    "百分之百",
    "彻底清除",
    "全部去除",
    "十年油污",
    "永不反弹",
    "神奇",
    "史上最",
    "立竿见影",
)


def usable_facts(facts: Iterable[Fact]) -> List[Fact]:
    """已确认事实，以及用户明确批准照原文使用的资料说法。"""
    usable = []
    for fact in facts:
        if fact.level in (ClaimLevel.INFERENCE, ClaimLevel.UNKNOWN):
            continue
        if fact.level == ClaimLevel.CONFIRMED and fact.approved:
            usable.append(fact)
        elif fact.level == ClaimLevel.SOURCE_CLAIM and fact.approved:
            usable.append(fact)
    return usable


def build_script_copy(
    segment_role: str,
    candidate_lines: List[str],
    facts: List[Fact],
    bound_material_shows_effect: bool,
) -> CopyDecision:
    decision = CopyDecision()
    allowed = usable_facts(facts)
    for line in candidate_lines:
        reason = rejection_reason(
            line,
            segment_role=segment_role,
            facts=allowed,
            bound_material_shows_effect=bound_material_shows_effect,
        )
        if reason:
            decision.rejected.append(reason)
        else:
            decision.accepted.append(line.strip())
    return decision


def rejection_reason(
    line: str,
    segment_role: str,
    facts: List[Fact],
    bound_material_shows_effect: bool,
) -> Optional[str]:
    text = (line or "").strip()
    if not text:
        return "空句子"
    for marker in EXAGGERATION_MARKERS:
        if marker in text and not any(marker in fact.text for fact in facts):
            return f"夸大表述不能进入口播：{marker}"
    matched = [fact for fact in facts if text == fact.text.strip() or text in fact.text]
    if not matched:
        return "这句话对不上已确认或已批准的事实"
    if segment_role == "effect":
        if not bound_material_shows_effect:
            return "没有拍到使用效果的素材，不能写效果"
        if not any(fact.kind == "observed_effect" for fact in matched):
            return "效果句必须对应画面里看得到的结果"
    return None
