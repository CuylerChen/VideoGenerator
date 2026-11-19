"""从参考视频截取短片段。原视频不进入成片时间轴。"""

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence


@dataclass
class ClipWindow:
    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass
class Material:
    material_id: str
    source_path: str
    clip_path: str
    kind: str
    shows_effect: bool = False
    start: float = 0.0
    end: float = 0.0
    usable_for: str = "any"


@dataclass
class SegmentBinding:
    role: str
    duration: float
    asset_path: str | None
    material_id: str | None
    shows_effect: bool
    source_path: str | None = None


TEMPLATE_SEGMENTS = {
    "goodthings_fast_30s": (
        ("hook", 3.0),
        ("reveal", 4.0),
        ("feature", 6.0),
        ("usage", 8.0),
        ("effect", 4.0),
        ("outro", 5.0),
    )
}

MAX_CLIP_SECONDS = 2.0


def plan_clip_windows(
    duration: float,
    max_clip: float = MAX_CLIP_SECONDS,
    max_windows: int = 4,
) -> List[ClipWindow]:
    """挑若干短窗口。长视频不会被规划成一个覆盖全片的窗口。"""
    if duration <= 0 or max_clip <= 0 or max_windows <= 0:
        return []
    clip_len = min(max_clip, duration)
    if duration <= max_clip:
        return [ClipWindow(0.0, round(duration, 3))]

    count = min(max_windows, max(1, int(duration // (max_clip + 1))))
    span = duration - clip_len
    if count == 1:
        start = span / 2
        return [ClipWindow(round(start, 3), round(start + clip_len, 3))]

    windows = []
    for index in range(count):
        start = span * index / (count - 1)
        windows.append(ClipWindow(round(start, 3), round(start + clip_len, 3)))
    if sum(window.duration for window in windows) >= duration:
        windows = windows[:-1]
    return windows


def bind_timeline(
    materials: Sequence[Material],
    template_id: str = "goodthings_fast_30s",
) -> List[SegmentBinding]:
    template = TEMPLATE_SEGMENTS[template_id]
    clips = [
        item
        for item in materials
        if item.kind == "video_clip" and item.clip_path and item.clip_path != item.source_path
    ]
    images = [item for item in materials if item.kind == "image" and item.clip_path]
    effect_clips = [item for item in clips if item.shows_effect]
    bindings: List[SegmentBinding] = []
    cursor = 0
    for role, duration in template:
        chosen = None
        if role == "effect":
            chosen = effect_clips[0] if effect_clips else (images[0] if images else None)
        elif clips:
            chosen = clips[cursor % len(clips)]
            cursor += 1
        elif images:
            chosen = images[0]

        if chosen is None:
            bindings.append(SegmentBinding(role, duration, None, None, False, None))
            continue
        bindings.append(
            SegmentBinding(
                role=role,
                duration=duration,
                asset_path=chosen.clip_path,
                material_id=chosen.material_id,
                shows_effect=bool(chosen.shows_effect and role == "effect"),
                source_path=chosen.source_path,
            )
        )
    return bindings


def probe_duration(path: str) -> float:
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            path,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(proc.stdout.strip())


def extract_clip(source: str, start: float, end: float, output: str) -> str:
    """按入点和出点导出短片段。拒绝把长参考视频整段导出。"""
    duration = end - start
    if duration <= 0:
        raise ValueError("片段时长必须大于 0")
    if duration > MAX_CLIP_SECONDS + 0.05:
        raise ValueError("单个参考片段不能超过 2 秒")
    source_duration = probe_duration(source)
    covers_source = start <= 0.05 and end >= source_duration - 0.05
    if covers_source and source_duration > MAX_CLIP_SECONDS:
        raise ValueError("不能把整段参考视频切成一个片段")

    Path(output).parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            source,
            "-ss",
            f"{start:.3f}",
            "-t",
            f"{duration:.3f}",
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            output,
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr[-500:] or "ffmpeg 截取失败")
    return output
