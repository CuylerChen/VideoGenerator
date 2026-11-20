"""28 秒快节奏模板。字幕跟着真实素材走，参考视频只以短片段进入分镜。"""

from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from pathlib import Path

from goodthings.fact_policy import EXAGGERATION_MARKERS
from goodthings.materials import Material, extract_clip, plan_clip_windows, probe_duration
from goodthings.scripting import BRAND_LINE

COMPARE_LINE = "清洁前后，一眼就能看出来。"
FOAM_LINE = "泡沫覆盖，针对厨房油污清洁。"
SAFE_USAGE = "对准需要清洁的油污区域，按照说明喷洒，等待后再擦拭。"

# 每镜 1–2 秒，合计 28 秒。
SHOT_SPECS = (
    (1.5, "hook", "grease"),
    (1.5, "hook", "grease"),
    (1.5, "reveal", "bottle"),
    (1.5, "reveal", "bottle"),
    (1.0, "reveal", "nozzle"),
    (1.5, "foam", "spray"),
    (1.5, "foam", "foam"),
    (1.5, "foam", "foam"),
    (1.5, "foam", "foam"),
    (1.5, "clean", "wipe"),
    (1.5, "clean", "wipe"),
    (1.5, "clean", "wipe"),
    (1.5, "clean", "wipe"),
    (2.0, "clean", "wipe"),
    (2.0, "compare", "before"),
    (2.0, "compare", "after"),
    (1.5, "outro", "product"),
    (1.5, "outro", "product"),
)

TAG_LABELS = {
    "bottle": "商品图",
    "nozzle": "喷头",
    "grease": "油污",
    "spray": "喷洒",
    "foam": "泡沫",
    "wipe": "擦拭",
    "before": "清洁前",
    "after": "清洁后",
    "product": "商品收尾",
}


@dataclass
class FastShot:
    start: float
    duration: float
    role: str
    slot: str
    caption: str
    asset_path: Optional[str] = None
    source_path: Optional[str] = None
    push_in: bool = False


@dataclass
class FastStoryboard:
    product_name: str
    voice_text: str
    shots: List[FastShot]
    total_duration: float = 28.0
    notes: List[str] = field(default_factory=list)


def safe_usage(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned or any(marker in cleaned for marker in EXAGGERATION_MARKERS):
        return SAFE_USAGE
    return cleaned


def collect_tags(materials: Sequence[Material]) -> set:
    return {item.usable_for for item in materials if item.usable_for and item.usable_for != "any"}


def build_voice(product_name: str, usage_text: str, tags: set) -> str:
    name = (product_name or "").strip() or "这款油污净"
    hook = "厨房灶台油污太难清理？" if "grease" in tags else "厨房清洁想省点力气？"
    kind = "泡沫型" if "foam" in tags else ""
    usage = safe_usage(usage_text)
    effect = "实际清洁效果怎么样？看完这个过程就知道了。"
    return f"{hook}试试这款{kind}{name}！{usage}{effect}{BRAND_LINE}"


def beat_caption(role: str, tags: set, product_name: str) -> str:
    name = (product_name or "").strip() or "油污净"
    if role == "hook":
        if "grease" in tags:
            return "厨房油污这么厚，真的太难清理了！"
        return "厨房油污，清理起来很费劲。"
    if role == "reveal":
        if "foam" in tags:
            return f"试试这款泡沫型{name}！"
        return f"试试这款{name}！"
    if role == "foam":
        if "foam" in tags:
            return FOAM_LINE
        return "对准油污喷洒，针对厨房油污清洁。"
    if role == "clean":
        return "擦拭看看，实际效果怎么样！"
    if role == "compare":
        if {"before", "after"} <= tags:
            return COMPARE_LINE
        return "擦拭看看这个过程。"
    return "厨房清洁好物，收藏起来！"


def _usable(item: Material) -> bool:
    if not item.clip_path:
        return False
    if item.kind == "video_clip" and item.clip_path == item.source_path:
        return False
    return True


def _pick(materials: Sequence[Material], slot: str, cursor: dict) -> Optional[Material]:
    tagged = [item for item in materials if item.usable_for == slot and _usable(item)]
    if not tagged and slot in {"bottle", "nozzle", "product"}:
        tagged = [item for item in materials if item.kind == "image" and _usable(item)]
    if not tagged and slot in {"wipe", "spray", "grease", "foam"}:
        tagged = [
            item
            for item in materials
            if item.kind == "video_clip"
            and item.usable_for not in {"before", "after"}
            and _usable(item)
        ]
    if not tagged:
        return None
    index = cursor.get(slot, 0)
    cursor[slot] = index + 1
    return tagged[index % len(tagged)]


def build_fast_storyboard(
    product_name: str,
    usage_text: str,
    materials: Sequence[Material],
) -> FastStoryboard:
    tags = collect_tags(materials)
    notes = []
    specs = []
    has_compare = {"before", "after"} <= tags
    if not has_compare:
        notes.append("没有清洁前和清洁后的真实画面，已去掉前后对比。")
    if "foam" not in tags:
        notes.append("没有泡沫画面，口播和字幕不写泡沫。")
    if "grease" not in tags:
        notes.append("没有厚油污画面，开场不说油污很厚。")

    for duration, role, slot in SHOT_SPECS:
        if role == "compare" and not has_compare:
            specs.append((duration, "clean", "wipe"))
        else:
            specs.append((duration, role, slot))

    cursor = {}
    shots = []
    clock = 0.0
    for duration, role, slot in specs:
        chosen = _pick(materials, slot, cursor)
        shots.append(
            FastShot(
                start=round(clock, 3),
                duration=duration,
                role=role,
                slot=slot,
                caption=beat_caption(role, tags, product_name),
                asset_path=chosen.clip_path if chosen else None,
                source_path=chosen.source_path if chosen else None,
                push_in=slot in {"bottle", "nozzle", "product"},
            )
        )
        clock += duration
    return FastStoryboard(
        product_name=product_name,
        voice_text=build_voice(product_name, usage_text, tags),
        shots=shots,
        total_duration=round(clock, 3),
        notes=notes,
    )


def materialize_file(source: str, tag: str, dest_dir: str, material_id: str) -> List[Material]:
    """图片直接引用。视频只导出不超过 2 秒的片段，原片不进入分镜。"""
    suffix = Path(source).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
        return [
            Material(
                material_id=material_id,
                source_path=source,
                clip_path=source,
                kind="image",
                usable_for=tag or "bottle",
            )
        ]
    duration = probe_duration(source)
    windows = plan_clip_windows(duration, max_clip=2.0, max_windows=3)
    if tag in {"before", "after"}:
        windows = windows[:1]
    materials = []
    folder = Path(dest_dir)
    folder.mkdir(parents=True, exist_ok=True)
    for index, window in enumerate(windows):
        clip_path = folder / f"{material_id}-{index}.mp4"
        extract_clip(source, window.start, window.end, str(clip_path))
        materials.append(
            Material(
                material_id=f"{material_id}-{index}",
                source_path=source,
                clip_path=str(clip_path),
                kind="video_clip",
                shows_effect=tag == "after",
                start=window.start,
                end=window.end,
                usable_for=tag or "wipe",
            )
        )
    return materials
