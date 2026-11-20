"""视频只在临时目录里活到下载完成。服务器不保留成片和参考视频。"""

import shutil
import time
from pathlib import Path
from typing import Iterable, Optional


def session_dir(root: str | Path, session_id: str) -> Path:
    folder = Path(root) / session_id
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def release_video(video_path: str, extra_paths: Optional[Iterable[str]] = None) -> bytes:
    """读出成片字节，然后删除服务器上的视频文件。"""
    path = Path(video_path)
    if not path.is_file():
        raise FileNotFoundError("找不到要下载的视频")
    data = path.read_bytes()
    path.unlink()
    for item in extra_paths or []:
        target = Path(item)
        if not target.exists():
            continue
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
    return data


def cleanup_older_than(root: str | Path, max_age_seconds: int = 6 * 3600) -> int:
    """清掉超时的临时目录，避免服务器磁盘留下视频。"""
    base = Path(root)
    if not base.exists():
        return 0
    removed = 0
    deadline = time.time() - max_age_seconds
    for child in base.iterdir():
        if not child.is_dir():
            continue
        if child.stat().st_mtime > deadline:
            continue
        shutil.rmtree(child, ignore_errors=True)
        removed += 1
    return removed
