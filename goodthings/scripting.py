"""根据已批准事实和剪辑素材生成可编辑脚本。"""

from dataclasses import dataclass, field
from typing import List, Sequence

from goodthings.fact_policy import Fact, build_script_copy
from goodthings.materials import TEMPLATE_SEGMENTS, Material, bind_timeline

BRAND_LINE = "每天发现一个实用好物，这里是好物研究所！"

ROLE_KINDS = {
    "hook": {"identity", "usage", "caution"},
    "reveal": {"identity", "spec", "description"},
    "feature": {"claim", "spec", "description"},
    "usage": {"usage", "caution"},
    "effect": {"observed_effect"},
    "outro": {"identity"},
}


@dataclass
class ScriptSegment:
    role: str
    duration: float
    voice_lines: List[str] = field(default_factory=list)
    caption: str = ""
    asset_path: str | None = None
    material_id: str | None = None
    shows_effect: bool = False
    source_path: str | None = None


@dataclass
class EditingScript:
    template_id: str
    segments: List[ScriptSegment]


def generate_editing_script(
    product_name: str,
    facts: Sequence[Fact],
    materials: Sequence[Material],
    template_id: str = "goodthings_fast_30s",
) -> EditingScript:
    if template_id not in TEMPLATE_SEGMENTS:
        raise KeyError(f"未知模板: {template_id}")
    bindings = bind_timeline(materials, template_id)
    segments = []
    for binding in bindings:
        candidates = [
            fact.text.strip()
            for fact in facts
            if fact.kind in ROLE_KINDS.get(binding.role, set()) and fact.text.strip()
        ]
        decision = build_script_copy(
            segment_role=binding.role,
            candidate_lines=candidates,
            facts=list(facts),
            bound_material_shows_effect=binding.shows_effect,
        )
        lines = list(decision.accepted)
        if binding.role == "outro":
            lines.append(BRAND_LINE)
        caption = lines[0] if lines else product_name
        segments.append(
            ScriptSegment(
                role=binding.role,
                duration=binding.duration,
                voice_lines=lines,
                caption=caption,
                asset_path=binding.asset_path,
                material_id=binding.material_id,
                shows_effect=binding.shows_effect,
                source_path=binding.source_path,
            )
        )
    return EditingScript(template_id=template_id, segments=segments)
