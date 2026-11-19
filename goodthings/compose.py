"""按脚本合成成片。只使用脚本点名的短片段和图片。"""

import subprocess
from pathlib import Path
from typing import Awaitable, Callable, List, Optional, Tuple

from goodthings.frames import render_frame, render_subtitle_overlay
from goodthings.scripting import BRAND_LINE, EditingScript

VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
TTSFunc = Callable[[str, str], Awaitable[str]]


def assert_segment_asset_allowed(asset_path: Optional[str], source_path: Optional[str]) -> None:
    if not asset_path or not source_path:
        return
    if Path(asset_path).resolve() == Path(source_path).resolve() and Path(asset_path).suffix.lower() in VIDEO_SUFFIXES:
        raise ValueError("参考视频不能整段进入成片")


def _run_ffmpeg(args: List[str]) -> None:
    proc = subprocess.run(["ffmpeg", "-y", *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr[-800:] or "ffmpeg 失败")


def render_silence(output: str, duration: float) -> str:
    _run_ffmpeg(
        [
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=44100:cl=mono",
            "-t",
            f"{max(duration, 0.4):.3f}",
            "-acodec",
            "libmp3lame",
            output,
        ]
    )
    return output


def fit_audio(source: str, duration: float, output: str) -> Tuple[str, Optional[str]]:
    from pixelle_video.services.video import VideoService

    actual = VideoService()._get_audio_duration(source)
    if actual > duration + 0.3:
        return source, f"口播长于镜头槽位 {duration:.1f} 秒，已保留完整口播，未从句中截断"
    _run_ffmpeg(
        [
            "-i",
            source,
            "-af",
            f"apad=whole_dur={duration:.3f}",
            "-t",
            f"{duration:.3f}",
            "-acodec",
            "libmp3lame",
            output,
        ]
    )
    return output, None


async def compose_script(
    script: EditingScript,
    output_path: str,
    work_dir: str,
    tts: TTSFunc,
    product_name: str,
    bgm_path: Optional[str] = None,
) -> Tuple[str, List[str]]:
    from pixelle_video.services.video import VideoService

    video = VideoService()
    folder = Path(work_dir)
    folder.mkdir(parents=True, exist_ok=True)
    warnings: List[str] = []
    segment_paths: List[str] = []

    for index, segment in enumerate(script.segments):
        assert_segment_asset_allowed(segment.asset_path, segment.source_path)
        spoken = "。".join(line for line in segment.voice_lines if line)
        audio_path = str(folder / f"{index:02d}_audio.mp3")
        if spoken:
            produced = await tts(spoken, audio_path)
        else:
            produced = render_silence(audio_path, segment.duration)
        fitted, warning = fit_audio(produced, segment.duration, str(folder / f"{index:02d}_fit.mp3"))
        if warning:
            warnings.append(f"{segment.role}: {warning}")
        caption = segment.caption or product_name
        slogan = BRAND_LINE if segment.role == "outro" else ""
        segment_out = str(folder / f"{index:02d}_segment.mp4")
        asset = segment.asset_path
        if asset and Path(asset).suffix.lower() in VIDEO_SUFFIXES:
            overlay = render_subtitle_overlay(str(folder / f"{index:02d}_sub.png"), caption, slogan)
            overlaid = str(folder / f"{index:02d}_overlaid.mp4")
            video.overlay_image_on_video(asset, overlay, overlaid, scale_mode="contain")
            video.merge_audio_video(overlaid, fitted, segment_out, replace_audio=True)
        else:
            frame = render_frame(
                str(folder / f"{index:02d}_frame.png"),
                caption=caption,
                title=product_name,
                image_path=asset,
                slogan=slogan,
            )
            video.create_video_from_image(frame, fitted, segment_out, fps=30)
        segment_paths.append(segment_out)

    final = video.concat_videos(
        segment_paths,
        output_path,
        bgm_path=bgm_path,
        bgm_volume=0.2,
        bgm_mode="loop",
    )
    return final, warnings
