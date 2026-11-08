"""作者：Wangyuan；日期：2026-10-29。职责：共享可读的艺术字幕字体和柔和文字绘制。"""

from __future__ import annotations

import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent


def art_font(style: str = "serif", size: int = 50) -> ImageFont.FreeTypeFont:
    """加载已授权字体；缺文件时明确报错，避免静默回到用户不满意的字形。"""
    if style not in {"serif", "hand"}:
        raise ValueError("请选择艺术宋体或手绘美术字")
    override = os.environ.get("VIDEO_SERIF_FONT" if style == "serif" else "VIDEO_HAND_FONT") or os.environ.get("VIDEO_FONT")
    if not override:
        raise ValueError("请设置 VIDEO_FONT 为已授权的本地字体路径")
    path = Path(override)
    if not path.is_file():
        raise ValueError(f"艺术字幕字体不存在：{path.name}")
    font = ImageFont.truetype(str(path), size)
    return font


def draw_soft_text(image: Image.Image, xy: tuple[float, float], text: str,
                   font: ImageFont.FreeTypeFont,
                   fill: tuple[int, int, int, int] = (255, 250, 238, 255)) -> None:
    """整行共用文字基线，以柔和投影提高识别度且保留英文和标点位置。"""
    x, y = xy
    scale = image.width / 1080
    if x < 78 * scale or x + font.getlength(text) > 880 * scale:
        raise ValueError("字幕超出竖屏安全区域，请缩短文字")
    baseline = y - font.getbbox(text, anchor="ls")[1]
    shadow = Image.new("RGBA", image.size)
    ImageDraw.Draw(shadow).text((x+1, baseline+2), text, font=font,
                               fill=(8, 16, 17, 160), anchor="ls")
    image.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(max(1, 3 * scale))))
    ImageDraw.Draw(image).text((x, baseline), text, font=font, fill=fill, anchor="ls")


def text_lines(text: str, font: ImageFont.FreeTypeFont, width: int = 774) -> list[str]:
    """根据真实字宽换行，避免使用固定字数使艺术字体越界。"""
    result: list[str] = []
    for paragraph in text.split("\n"):
        line = ""
        for char in paragraph:
            if line and font.getlength(line + char) > width:
                result.append(line)
                line = char
            else:
                line += char
        if line:
            result.append(line)
    return result
