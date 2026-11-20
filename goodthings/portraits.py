"""去掉别人的人像。默认不让人脸进入成片。"""

import subprocess
import tempfile
from pathlib import Path
from typing import Callable, List, Sequence, Tuple

from goodthings.materials import Material

VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
CASCADE_PATH = Path(__file__).resolve().parent / "assets" / "haarcascade_frontalface_default.xml"


def exclude_portraits(
    materials: Sequence[Material],
    contains_face: Callable[[str], bool],
) -> Tuple[List[Material], int]:
    kept: List[Material] = []
    dropped = 0
    for item in materials:
        if item.clip_path and contains_face(item.clip_path):
            dropped += 1
            continue
        kept.append(item)
    return kept, dropped


def contains_face(path: str) -> bool:
    """检测图片或短片段里有没有正面人脸。"""
    target = Path(path)
    if not target.exists():
        return False
    frames = _sample_frames(target)
    try:
        return any(_frame_has_face(frame) for frame in frames)
    finally:
        for frame in frames:
            if frame != target and frame.exists():
                frame.unlink(missing_ok=True)


def _sample_frames(path: Path) -> List[Path]:
    if path.suffix.lower() in IMAGE_SUFFIXES:
        return [path]
    if path.suffix.lower() not in VIDEO_SUFFIXES:
        return []
    frames = []
    for fraction in (0.2, 0.5, 0.8):
        frame = Path(tempfile.mkstemp(suffix=".jpg")[1])
        proc = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                str(_seek(path, fraction)),
                "-i",
                str(path),
                "-frames:v",
                "1",
                str(frame),
            ],
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0 and frame.exists() and frame.stat().st_size > 0:
            frames.append(frame)
        elif frame.exists():
            frame.unlink(missing_ok=True)
    return frames


def _seek(path: Path, fraction: float) -> float:
    from goodthings.materials import probe_duration

    try:
        duration = probe_duration(str(path))
    except Exception:
        return 0.0
    return max(0.0, duration * fraction - 0.05)


def _frame_has_face(path: Path) -> bool:
    import cv2

    if not CASCADE_PATH.exists():
        raise FileNotFoundError("缺少人脸检测模型")
    image = cv2.imread(str(path))
    if image is None:
        return False
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    cascade = cv2.CascadeClassifier(str(CASCADE_PATH))
    faces = cascade.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=7,
        minSize=(48, 48),
    )
    return len(faces) > 0
