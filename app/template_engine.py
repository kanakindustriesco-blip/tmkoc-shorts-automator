import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from app.config import (
    TARGET_WIDTH,
    TARGET_HEIGHT,
    VIDEO_WINDOW_Y_START,
    VIDEO_WINDOW_HEIGHT,
    EPISODE_PILL_CENTER,
    PART_PILL_CENTER,
    DEFAULT_TEMPLATE_PATH
)

def get_font(size: int, bold: bool = True):
    font_candidates = [
        r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\impact.ttf",
        r"C:\Windows\Fonts\segoeuib.ttf" if bold else r"C:\Windows\Fonts\segoeui.ttf",
        r"C:\Windows\Fonts\trebucbd.ttf",
        r"C:\Windows\Fonts\tahomabd.ttf",
    ]
    for font_path in font_candidates:
        if os.path.exists(font_path):
            try:
                return ImageFont.truetype(font_path, size)
            except Exception:
                continue
    return ImageFont.load_default()

def draw_centered_text(draw: ImageDraw.ImageDraw, center_pos, text: str, font, fill_color=(10, 20, 90)):
    """
    Renders text centered horizontally and vertically around center_pos.
    """
    cx, cy = center_pos
    bbox = font.getbbox(text)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    # Y-offset adjustment for visual baseline centering
    draw.text((cx - w / 2, cy - h / 2 - 3), text, font=font, fill=fill_color)
    return w, h

def create_official_tmkoc_overlay(episode_num: str, part_num: int, template_path: str = None) -> Image.Image:
    """
    Takes user's ===.png template, resizes to 1080x1920,
    makes center video window (y=623 to 1241) transparent,
    and draws episode number and part number in the pill boxes.
    """
    tpl_file = template_path if (template_path and os.path.exists(template_path)) else str(DEFAULT_TEMPLATE_PATH)
    
    base = Image.open(tpl_file).convert("RGBA")
    if base.size != (TARGET_WIDTH, TARGET_HEIGHT):
        base = base.resize((TARGET_WIDTH, TARGET_HEIGHT), Image.Resampling.LANCZOS)

    # 1. Punch out center video window so 16:9 video plays underneath
    clear_window = Image.new("RGBA", (TARGET_WIDTH, VIDEO_WINDOW_HEIGHT), (0, 0, 0, 0))
    base.paste(clear_window, (0, VIDEO_WINDOW_Y_START))

    draw = ImageDraw.Draw(base)

    # 2. Draw Episode Number inside EPISODE NO. pill box
    # Font size adapts if episode number is long (e.g. 4 digits like 1500)
    ep_str = str(episode_num).strip()
    ep_font_size = 44 if len(ep_str) <= 3 else 36
    ep_font = get_font(ep_font_size, bold=True)
    draw_centered_text(draw, EPISODE_PILL_CENTER, ep_str, ep_font, fill_color=(12, 22, 95))

    # 3. Draw Part Number inside PART NO. pill box
    pt_str = str(part_num).strip()
    pt_font_size = 44 if len(pt_str) <= 2 else 38
    pt_font = get_font(pt_font_size, bold=True)
    draw_centered_text(draw, PART_PILL_CENTER, pt_str, pt_font, fill_color=(12, 22, 95))

    return base

def generate_part_overlay(episode_num: str, part_num: int, custom_template_path: str = None, **kwargs) -> Image.Image:
    """
    Main entry point to get overlay image for each part.
    """
    return create_official_tmkoc_overlay(episode_num, part_num, custom_template_path)

def generate_preview_mockup(episode_num: str, part_num: int, custom_template_path: str = None, sample_frame_path: str = None, output_path: str = None) -> str:
    """
    Generates 1080x1920 preview with sample frame centered in the video window.
    """
    overlay = generate_part_overlay(episode_num, part_num, custom_template_path)

    canvas = Image.new("RGB", (TARGET_WIDTH, TARGET_HEIGHT), (0, 0, 0))

    if sample_frame_path and os.path.exists(sample_frame_path):
        frame = Image.open(sample_frame_path).convert("RGB")
        frame = frame.resize((TARGET_WIDTH, VIDEO_WINDOW_HEIGHT), Image.Resampling.LANCZOS)
        canvas.paste(frame, (0, VIDEO_WINDOW_Y_START))
    else:
        # Placeholder episode frame
        draw_preview = ImageDraw.Draw(canvas)
        draw_preview.rectangle([0, VIDEO_WINDOW_Y_START, TARGET_WIDTH, VIDEO_WINDOW_Y_START + VIDEO_WINDOW_HEIGHT], fill=(25, 30, 42))
        font_sample = get_font(48, bold=True)
        draw_preview.text((TARGET_WIDTH // 2 - 220, VIDEO_WINDOW_Y_START + (VIDEO_WINDOW_HEIGHT // 2) - 25), "16:9 TMKOC EPISODE", font=font_sample, fill=(220, 230, 255))

    # Paste overlay with transparency
    canvas.paste(overlay, (0, 0), overlay)

    if not output_path:
        output_path = "preview.jpg"

    canvas.save(output_path, "JPEG", quality=92)
    return output_path
