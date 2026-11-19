"""把商品图和字幕画成 1080×1920 画面。"""

from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

FRAME_SIZE = (1080, 1920)
FONT_CANDIDATES = (
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
)


def find_cjk_font() -> Optional[str]:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return path
    return None


def _font(size: int) -> ImageFont.ImageFont:
    path = find_cjk_font()
    if path:
        return ImageFont.truetype(path, size, index=0)
    return ImageFont.load_default()


def wrap_text(text: str, width: int = 14) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    return "\n".join(text[index : index + width] for index in range(0, len(text), width))


def render_frame(
    output: str,
    caption: str,
    title: str = "",
    image_path: Optional[str] = None,
    slogan: str = "",
) -> str:
    canvas = Image.new("RGB", FRAME_SIZE, (16, 16, 16))
    if image_path and Path(image_path).exists() and Path(image_path).suffix.lower() in {
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
    }:
        photo = Image.open(image_path).convert("RGB")
        photo.thumbnail((960, 1280))
        left = (FRAME_SIZE[0] - photo.width) // 2
        canvas.paste(photo, (left, 180))
    draw = ImageDraw.Draw(canvas)
    if title:
        draw.text((60, 60), title, font=_font(42), fill=(255, 255, 255))
    draw.multiline_text(
        (60, 1500),
        wrap_text(caption),
        font=_font(60),
        fill=(255, 255, 255),
        spacing=10,
    )
    if slogan:
        draw.text((60, 1820), slogan, font=_font(32), fill=(210, 210, 210))
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output)
    return output


def render_subtitle_overlay(output: str, caption: str, slogan: str = "") -> str:
    canvas = Image.new("RGBA", FRAME_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    overlay = Image.new("RGBA", (FRAME_SIZE[0], 420), (0, 0, 0, 140))
    canvas.alpha_composite(overlay, (0, 1500))
    draw.multiline_text(
        (60, 1540),
        wrap_text(caption),
        font=_font(56),
        fill=(255, 255, 255, 255),
        spacing=8,
    )
    if slogan:
        draw.text((60, 1820), slogan, font=_font(32), fill=(255, 255, 255, 255))
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output)
    return output
