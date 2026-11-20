"""商品文案必须实事求是，参考视频不能整段进入成片。"""

from goodthings.fact_policy import ClaimLevel, Fact, build_script_copy
from goodthings.materials import Material, bind_timeline, plan_clip_windows
from goodthings.scripting import generate_editing_script


def test_inference_does_not_enter_voiceover():
    facts = [
        Fact(
            fact_id="name",
            text="商品名称是净浮生油污净",
            level=ClaimLevel.CONFIRMED,
            kind="identity",
            approved=True,
        ),
        Fact(
            fact_id="guess",
            text="能一次清除十年油污",
            level=ClaimLevel.INFERENCE,
            kind="effect",
            approved=False,
        ),
    ]

    result = build_script_copy(
        segment_role="effect",
        candidate_lines=["能一次清除十年油污"],
        facts=facts,
        bound_material_shows_effect=False,
    )

    assert result.accepted == []
    assert result.rejected


def test_exaggeration_absent_from_source_is_rejected():
    facts = [
        Fact(
            fact_id="usage",
            text="将油污净喷在灶台表面",
            level=ClaimLevel.CONFIRMED,
            kind="usage",
            approved=True,
        )
    ]

    result = build_script_copy(
        segment_role="usage",
        candidate_lines=["喷上后油污立即消失，一次搞定"],
        facts=facts,
        bound_material_shows_effect=False,
    )

    assert result.accepted == []


def test_confirmed_sentence_matching_source_is_kept():
    facts = [
        Fact(
            fact_id="usage",
            text="将油污净喷在灶台表面",
            level=ClaimLevel.CONFIRMED,
            kind="usage",
            approved=True,
        )
    ]

    result = build_script_copy(
        segment_role="usage",
        candidate_lines=["将油污净喷在灶台表面"],
        facts=facts,
        bound_material_shows_effect=False,
    )

    assert result.accepted == ["将油污净喷在灶台表面"]


def test_unapproved_source_claim_does_not_enter_voiceover():
    facts = [
        Fact(
            fact_id="pack",
            text="包装写着去油污",
            level=ClaimLevel.SOURCE_CLAIM,
            kind="effect",
            approved=False,
        )
    ]

    result = build_script_copy(
        segment_role="intro",
        candidate_lines=["包装写着去油污"],
        facts=facts,
        bound_material_shows_effect=False,
    )

    assert result.accepted == []


def test_effect_sentence_requires_a_clip_that_shows_the_effect():
    facts = [
        Fact(
            fact_id="seen",
            text="擦拭后灶台表面的油污减少",
            level=ClaimLevel.CONFIRMED,
            kind="observed_effect",
            approved=True,
        )
    ]
    line = ["擦拭后灶台表面的油污减少"]

    blocked = build_script_copy(
        segment_role="effect",
        candidate_lines=line,
        facts=facts,
        bound_material_shows_effect=False,
    )
    allowed = build_script_copy(
        segment_role="effect",
        candidate_lines=line,
        facts=facts,
        bound_material_shows_effect=True,
    )

    assert blocked.accepted == []
    assert allowed.accepted == line


def test_long_reference_video_is_cut_into_short_windows():
    windows = plan_clip_windows(28.0, max_clip=2.0, max_windows=4)

    assert windows
    assert all(window.duration <= 2.0 for window in windows)
    assert sum(window.duration for window in windows) < 28.0
    assert not any(window.start == 0 and window.end == 28 for window in windows)


def test_timeline_uses_clip_files_not_the_reference_video():
    materials = [
        Material(
            material_id="clip-1",
            source_path="/library/ref-a.mp4",
            clip_path="/library/clips/clip-1.mp4",
            kind="video_clip",
            shows_effect=False,
            start=4.0,
            end=5.5,
        ),
        Material(
            material_id="still-1",
            source_path="/library/main.jpg",
            clip_path="/library/main.jpg",
            kind="image",
            shows_effect=False,
            start=0,
            end=0,
        ),
    ]

    bindings = bind_timeline(materials, template_id="goodthings_fast_30s")
    used_paths = [binding.asset_path for binding in bindings if binding.asset_path]

    assert used_paths
    assert "/library/ref-a.mp4" not in used_paths
    assert all(path != "/library/ref-a.mp4" for path in used_paths)


def test_generated_script_drops_ungrounded_effect_copy():
    facts = [
        Fact(
            fact_id="name",
            text="商品名称是净浮生油污净",
            level=ClaimLevel.CONFIRMED,
            kind="identity",
            approved=True,
        ),
        Fact(
            fact_id="guess",
            text="能一次清除十年油污",
            level=ClaimLevel.INFERENCE,
            kind="effect",
            approved=False,
        ),
    ]
    materials = [
        Material(
            material_id="still-1",
            source_path="/library/main.jpg",
            clip_path="/library/main.jpg",
            kind="image",
            shows_effect=False,
            start=0,
            end=0,
        )
    ]

    script = generate_editing_script(
        product_name="净浮生油污净",
        facts=facts,
        materials=materials,
        template_id="goodthings_fast_30s",
    )

    spoken = " ".join(line for segment in script.segments for line in segment.voice_lines)
    assert "一次清除" not in spoken
    assert "十年油污" not in spoken
    assert script.segments[-1].voice_lines[-1] == "每天发现一个实用好物，这里是好物研究所！"


def test_analysis_copies_user_text_and_does_not_invent_effects():
    from goodthings.analysis import facts_from_product

    facts = facts_from_product(
        {
            "product_id": "p1",
            "name": "净浮生油污净",
            "intro": "厨房油污清洁剂",
            "selling_points": "",
            "usage": "喷在表面后擦拭",
            "cautions": "",
            "spec": "",
        }
    )
    texts = [fact.text for fact in facts]

    assert "厨房油污清洁剂" in texts
    assert "喷在表面后擦拭" in texts
    assert all("一次清除" not in text for text in texts)
    intro = next(fact for fact in facts if fact.text == "厨房油污清洁剂")
    assert intro.approved is False


def test_extract_clip_is_shorter_than_the_reference(tmp_path):
    import subprocess

    from goodthings.materials import extract_clip, probe_duration

    source = tmp_path / "ref.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=320x240:d=4",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=44100:cl=mono",
            "-shortest",
            "-t",
            "4",
            str(source),
        ],
        check=True,
        capture_output=True,
    )
    clip = tmp_path / "clip.mp4"
    extract_clip(str(source), 1.0, 2.5, str(clip))

    assert clip.exists()
    assert probe_duration(str(clip)) < probe_duration(str(source))
    assert str(clip) != str(source)


async def test_compose_builds_vertical_mp4_from_a_product_image(tmp_path):
    import subprocess
    from pathlib import Path

    from PIL import Image

    from goodthings.compose import compose_script, render_silence
    from goodthings.scripting import EditingScript, ScriptSegment

    image = tmp_path / "main.jpg"
    Image.new("RGB", (240, 240), (30, 90, 40)).save(image)
    script = EditingScript(
        template_id="goodthings_fast_30s",
        segments=[
            ScriptSegment(
                role="reveal",
                duration=1.0,
                voice_lines=[],
                caption="商品名称是净浮生油污净",
                asset_path=str(image),
            )
        ],
    )

    async def speak(text: str, output_path: str) -> str:
        return render_silence(output_path, 0.8)

    final, _warnings = await compose_script(
        script,
        str(tmp_path / "final.mp4"),
        str(tmp_path / "work"),
        speak,
        "净浮生油污净",
    )
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0",
            final,
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert Path(final).stat().st_size > 1000
    assert probe.stdout.strip() == "1080,1920"


def test_fast_storyboard_cuts_every_one_to_two_seconds():
    from goodthings.fast_cut import build_fast_storyboard

    board = build_fast_storyboard("净浮生油污净", "对准油污喷洒，等待后再擦拭。", [])

    assert board.total_duration == 28
    assert all(1 <= shot.duration <= 2 for shot in board.shots)
    assert round(sum(shot.duration for shot in board.shots), 3) == 28


def test_before_after_line_requires_real_before_and_after():
    from goodthings.fast_cut import build_fast_storyboard
    from goodthings.materials import Material

    missing = build_fast_storyboard("净浮生油污净", "", [])
    spoken = " ".join(shot.caption for shot in missing.shots) + missing.voice_text
    assert "清洁前后，一眼就能看出来" not in spoken

    ready = build_fast_storyboard(
        "净浮生油污净",
        "",
        [
            Material("b", "/raw/before.mp4", "/clips/before.mp4", "video_clip", False, 0, 2, "before"),
            Material("a", "/raw/after.mp4", "/clips/after.mp4", "video_clip", True, 0, 2, "after"),
        ],
    )
    assert any("清洁前后，一眼就能看出来" in shot.caption for shot in ready.shots)
    used = [shot.asset_path for shot in ready.shots]
    assert "/raw/before.mp4" not in used
    assert "/raw/after.mp4" not in used


def test_foam_wording_requires_foam_footage():
    from goodthings.fast_cut import build_fast_storyboard
    from goodthings.materials import Material

    plain = build_fast_storyboard("净浮生油污净", "", [])
    assert "泡沫" not in plain.voice_text
    assert all("泡沫覆盖" not in shot.caption for shot in plain.shots)

    foamy = build_fast_storyboard(
        "净浮生油污净",
        "",
        [Material("f", "/raw/foam.mp4", "/clips/foam.mp4", "video_clip", False, 0, 2, "foam")],
    )
    assert "泡沫" in foamy.voice_text


def test_release_video_hands_bytes_to_the_browser_and_deletes_server_files(tmp_path):
    from goodthings.ephemeral import release_video

    video = tmp_path / "final.mp4"
    clip = tmp_path / "clip.mp4"
    video.write_bytes(b"final-bytes")
    clip.write_bytes(b"clip")

    data = release_video(str(video), extra_paths=[str(clip)])

    assert data == b"final-bytes"
    assert not video.exists()
    assert not clip.exists()


def test_storyboard_drops_other_peoples_portraits():
    from goodthings.fast_cut import build_fast_storyboard
    from goodthings.materials import Material
    from goodthings.portraits import exclude_portraits

    materials = [
        Material("face", "/raw/person.mp4", "/clips/person.mp4", "video_clip", False, 0, 2, "wipe"),
        Material("bottle", "/raw/bottle.jpg", "/raw/bottle.jpg", "image", False, 0, 0, "bottle"),
    ]
    kept, dropped = exclude_portraits(
        materials,
        contains_face=lambda path: path.endswith("person.mp4"),
    )
    board = build_fast_storyboard("净浮生油污净", "", kept)

    assert dropped == 1
    used = [shot.asset_path for shot in board.shots]
    assert "/clips/person.mp4" not in used
    assert "/raw/bottle.jpg" in used


def test_compose_refuses_to_splice_the_reference_video():
    from goodthings.compose import assert_segment_asset_allowed

    try:
        assert_segment_asset_allowed("/library/ref.mp4", "/library/ref.mp4")
    except ValueError as exc:
        assert "不能整段" in str(exc)
    else:
        raise AssertionError("整段参考视频不应被接受")
