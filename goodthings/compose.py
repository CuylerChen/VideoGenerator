"""按脚本合成成片。只使用脚本点名的短片段和图片。"""

from goodthings.fast_cut import FastStoryboard

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


def render_shot_video(shot_image: str, duration: float, output: str, push_in: bool = False) -> str:
    """把一帧做成 1–2 秒的 1080×1920 镜头。商品图可做快速推近。"""
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    if push_in:
        frames = max(int(duration * 30), 1)
        _run_ffmpeg(
            [
                "-loop",
                "1",
                "-i",
                shot_image,
                "-vf",
                (
                    f"scale=1280:2276:force_original_aspect_ratio=increase,"
                    f"crop=1080:1920:'(iw-1080)*t/{duration:.3f}':'(ih-1920)/2',"
                    f"fps=30,format=yuv420p"
                ),
                "-t",
                f"{duration:.3f}",
                "-frames:v",
                str(frames),
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                output,
            ]
        )
        return output
    _run_ffmpeg(
        [
            "-loop",
            "1",
            "-i",
            shot_image,
            "-vf",
            "scale=1080:1920,fps=30,format=yuv420p",
            "-t",
            f"{duration:.3f}",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            output,
        ]
    )
    return output


def render_clip_shot(clip_path: str, overlay_path: str, duration: float, output: str) -> str:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    _run_ffmpeg(
        [
            "-i",
            clip_path,
            "-i",
            overlay_path,
            "-filter_complex",
            (
                "[0:v]scale=1080:1920:force_original_aspect_ratio=decrease,"
                "pad=1080:1920:(ow-iw)/2:(oh-ih)/2,fps=30,format=yuv420p[v];"
                "[v][1:v]overlay=0:0"
            ),
            "-t",
            f"{duration:.3f}",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            output,
        ]
    )
    return output


async def compose_fast(
    storyboard: FastStoryboard,
    output_path: str,
    work_dir: str,
    tts: TTSFunc,
    bgm_path: Optional[str] = None,
) -> Tuple[str, List[str]]:
    """按固定 1–2 秒镜头合成。口播是一整条，不按镜头拆开截断。"""
    from pixelle_video.services.video import VideoService

    video = VideoService()
    folder = Path(work_dir)
    folder.mkdir(parents=True, exist_ok=True)
    from goodthings.portraits import contains_face

    warnings: List[str] = list(storyboard.notes)
    shot_paths: List[str] = []
    dropped_faces = 0
    for index, shot in enumerate(storyboard.shots):
        if shot.asset_path and contains_face(shot.asset_path):
            shot.asset_path = None
            shot.source_path = None
            dropped_faces += 1
        assert_segment_asset_allowed(shot.asset_path, shot.source_path)
        slogan = "每天发现一个实用好物，这里是好物研究所！" if shot.role == "outro" else ""
        asset = shot.asset_path
        shot_out = str(folder / f"{index:02d}_shot.mp4")
        if asset and Path(asset).suffix.lower() in VIDEO_SUFFIXES:
            overlay = render_subtitle_overlay(
                str(folder / f"{index:02d}_sub.png"),
                shot.caption,
                slogan,
            )
            render_clip_shot(asset, overlay, shot.duration, shot_out)
        else:
            frame = render_frame(
                str(folder / f"{index:02d}_frame.png"),
                caption=shot.caption,
                title=storyboard.product_name,
                image_path=asset,
                slogan=slogan,
            )
            render_shot_video(frame, shot.duration, shot_out, push_in=shot.push_in and bool(asset))
        shot_paths.append(shot_out)

    silent = str(folder / "silent.mp4")
    video.concat_videos(shot_paths, silent)
    voice_path = str(folder / "voice.mp3")
    produced = await tts(storyboard.voice_text, voice_path)
    voice_duration = video._get_audio_duration(produced)
    if dropped_faces:
        warnings.append(f"成片前又去掉了 {dropped_faces} 个含有人像的画面。")
    if voice_duration > 30:
        warnings.append("口播长于 30 秒，已保留完整句子，成片会略长于 28 秒")
        fitted = produced
    else:
        fitted, _warning = fit_audio(produced, storyboard.total_duration, str(folder / "voice_fit.mp3"))
    voiced = str(folder / "voiced.mp4")
    video.merge_audio_video(silent, fitted, voiced, replace_audio=True)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    if bgm_path and Path(bgm_path).exists():
        mix_quiet_bgm(voiced, bgm_path, output_path, volume=0.12)
    else:
        Path(voiced).replace(output_path)
    return output_path, warnings


def mix_quiet_bgm(video_path: str, bgm_path: str, output: str, volume: float = 0.12) -> str:
    """背景音乐低于旁白，不把口播音量压下去。"""
    _run_ffmpeg(
        [
            "-i",
            video_path,
            "-stream_loop",
            "-1",
            "-i",
            bgm_path,
            "-filter_complex",
            f"[1:a]volume={volume}[bg];[0:a][bg]amix=inputs=2:duration=first:dropout_transition=0:normalize=0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-shortest",
            output,
        ]
    )
    return output
