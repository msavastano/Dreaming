"""
Main build script for the Lorekeeper 45-second pixel art action video.

Supports:
  1. Generating the 3-frame contact sheet at (8s, 22s, 38s) to verify composition
     before running the full 2,700-frame render.
  2. Writing the timestamped Voiceover Script (VO_SCRIPT.md).
  3. Synthesizing the 100%-code soundtrack + voiceover and encoding the final
     1920x1080 @ 60fps H.264/AAC MP4 video.
"""

import argparse
import os
import subprocess
import tempfile
import time
from typing import List, Optional
import numpy as np
from PIL import Image, ImageDraw

from video.audio import generate_full_soundtrack, save_wav
from video.config import (
    CONTACT_SHEET_TIMESTAMPS,
    FPS,
    HEIGHT,
    SCENES,
    TOTAL_DURATION,
    TOTAL_FRAMES,
    WIDTH,
    get_scene_at_time,
)
from video.scenes import get_font, render_frame


VIDEO_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONTACT_SHEET_PATH = os.path.join(VIDEO_DIR, "contact_sheet_8s_22s_38s.png")
DEFAULT_VO_SCRIPT_PATH = os.path.join(VIDEO_DIR, "VO_SCRIPT.md")
DEFAULT_MP4_PATH = os.path.join(VIDEO_DIR, "lorekeeper_pixel_action.mp4")


def build_contact_sheet(
    output_path: str = DEFAULT_CONTACT_SHEET_PATH,
    audio_envelope: Optional[np.ndarray] = None,
) -> str:
    """
    Render the 3-frame contact sheet at CONTACT_SHEET_TIMESTAMPS (8s, 22s, 38s)
    arranged with full composition metadata headers and a high-res 3-up layout.
    """
    timestamps = CONTACT_SHEET_TIMESTAMPS
    frames: List[Image.Image] = []
    for ts in timestamps:
        f_idx = min(TOTAL_FRAMES - 1, max(0, int(round(ts * FPS))))
        frames.append(render_frame(f_idx, audio_envelope=audio_envelope))

    # Build a crisp vertical + horizontal studio contact sheet (1920 x 1460)
    # Top row: 3 side-by-side overview cards; Bottom rows: large detailed inspection panels
    sheet_w = 1920
    card_w = 600
    card_h = 338  # Exact 16:9 downscale of 1920x1080
    sheet_h = 112 + card_h + 72 + 540 + 40

    sheet = Image.new("RGB", (sheet_w, sheet_h), (16, 14, 12))
    draw = ImageDraw.Draw(sheet)

    # Header banner
    draw.rectangle([0, 0, sheet_w, 86], fill=(28, 24, 19))
    draw.line([(0, 86), (sheet_w, 86)], fill=(217, 165, 74), width=2)
    draw.text(
        (36, 18),
        "LOREKEEPER — 3-FRAME COMPOSITION CONTACT SHEET (8s, 22s, 38s)",
        font=get_font("serif_bold", 26),
        fill=(217, 165, 74),
    )
    draw.text(
        (36, 52),
        "Spec: 1920x1080 @ 60 FPS  |  Duration: 45.0s (2,700 frames)  |  Concept: Campaign VO reads text while pixel art is STILL, then unleashes 60fps ACTION",
        font=get_font("mono", 14),
        fill=(195, 184, 164),
    )

    # Row 1: 3-up side-by-side comparison at t = 8s, 22s, 38s
    margin_x = 30
    gap_x = 30
    row1_y = 108
    for idx, (ts, frm) in enumerate(zip(timestamps, frames)):
        sc, is_act, prog = get_scene_at_time(ts)
        cx = margin_x + idx * (card_w + gap_x)
        thumb = frm.resize((card_w, card_h), Image.Resampling.LANCZOS)
        sheet.paste(thumb, (cx, row1_y))
        draw.rectangle(
            [cx - 2, row1_y - 2, cx + card_w + 2, row1_y + card_h + 2],
            outline=(95, 225, 145) if is_act else (217, 165, 74),
            width=2,
        )
        f_num = int(round(ts * FPS))
        caption = f"FRAME {idx + 1} @ {ts:04.1f}s (#{f_num:04d}) • {sc.title}"
        subcap = f"ACTION 60FPS ({prog * 100:.0f}%) • {sc.location} ({sc.turn_id})"
        draw.text((cx, row1_y + card_h + 10), caption, font=get_font("mono_bold", 13), fill=(236, 228, 212))
        draw.text((cx, row1_y + card_h + 30), subcap, font=get_font("sans", 13), fill=(168, 156, 134))

    # Row 2: Zoomed 1:1 Pixel Art Viewport Crops from 8s, 22s, 38s to verify pixel-art crispness
    row2_title_y = row1_y + card_h + 64
    draw.line([(30, row2_title_y), (sheet_w - 30, row2_title_y)], fill=(58, 52, 42), width=1)
    draw.text(
        (36, row2_title_y + 10),
        "1:1 PIXEL ART ACTION VIEWPORT CROPS (VERIFYING CHARACTER READABILITY, SLASH ARCS, SPARKS & LIGHTING AT 8s, 22s, 38s):",
        font=get_font("mono_bold", 14),
        fill=(217, 165, 74),
    )

    crop_y = row2_title_y + 38
    crop_h = 460
    for idx, (ts, frm) in enumerate(zip(timestamps, frames)):
        cx = margin_x + idx * (card_w + gap_x)
        # Crop center-action region of the pixel viewport (40..1400, 84..740)
        vp_crop = frm.crop((160, 180, 1360, 740)).resize((card_w, crop_h), Image.Resampling.NEAREST)
        sheet.paste(vp_crop, (cx, crop_y))
        draw.rectangle(
            [cx - 2, crop_y - 2, cx + card_w + 2, crop_y + crop_h + 2],
            outline=(217, 165, 74),
            width=2,
        )
        draw.rounded_rectangle(
            [cx + 12, crop_y + 12, cx + 290, crop_y + 42],
            radius=5,
            fill=(20, 18, 15),
            outline=(217, 165, 74),
        )
        draw.text(
            (cx + 22, crop_y + 19),
            f"T = {ts:04.1f}s  •  4x PIXEL DETAIL",
            font=get_font("mono_bold", 14),
            fill=(255, 230, 135),
        )

    sheet.save(output_path, "PNG")
    return output_path


def write_vo_script(vo_metadata: List[dict], output_path: str = DEFAULT_VO_SCRIPT_PATH) -> str:
    """Write the complete timestamped Voiceover Script & Scene Breakdown to Markdown."""
    lines = [
        "# Lorekeeper — Voiceover (VO) Script & Scene Timestamps",
        "",
        "- **Project**: Lorekeeper (`msavastano/Dreaming`) — Thornwick Campaign Action Trailer",
        "- **Format**: `1920x1080`, `60 fps`, `45.00 seconds` (`2,700 frames`)",
        "- **Audio & Voiceover**: 100% generated in code (`video/audio.py` via `ffmpeg` `libflite` `rms` voice + NumPy procedural SFX & 16-bit synth score)",
        "- **Visual Rhythm**: In every scene, the **pixel art remains completely STILL** while the Voiceover reads the campaign text aloud and the text types onto the console. The moment the VO finishes reading, the scene transitions into **60fps PIXEL ART ACTION**.",
        "",
        "---",
        "",
        "## Master Timeline & Phase Overview",
        "",
        "| Scene | Act / Location | Turn ID | Still + VO Phase | Pixel Action Phase | Contact Sheet Check |",
        "| :---: | :--- | :---: | :---: | :---: | :---: |",
    ]

    cs_map = {1: "8.0s", 2: "22.0s", 3: "38.0s", 4: "—"}
    for sc in SCENES:
        lines.append(
            f"| **{sc.scene_id}** | {sc.title} ({sc.location}) | `{sc.turn_id}` | "
            f"`{sc.start:05.2f}s – {sc.still_end:05.2f}s` | "
            f"`{sc.still_end:05.2f}s – {sc.end:05.2f}s` | "
            f"**{cs_map.get(sc.scene_id, '—')}** |"
        )

    lines.extend(
        [
            "",
            "---",
            "",
            "## Timestamped Voiceover (VO) Script & Action Cues",
            "",
        ]
    )

    for sc, meta in zip(SCENES, vo_metadata):
        vo_s = meta["vo_start"]
        vo_e = meta["vo_end"]
        lines.extend(
            [
                f"### Scene {sc.scene_id}: {sc.title}",
                f"- **Scene Window**: `{sc.start:05.2f}s – {sc.end:05.2f}s` (Frames `{int(sc.start * FPS):04d} – {int(sc.end * FPS) - 1:04d}`)",
                f"- **Campaign Turn ID**: `{sc.turn_id}`",
                f"- **On-Screen Player Move**: `You > {sc.player_move}`",
                f"- **Phase 1 — PIXEL STILL + VOICEOVER (`{sc.start:05.2f}s – {sc.still_end:05.2f}s`)**:",
                f"  - **VO Timestamp**: `{vo_s:05.2f}s – {vo_e:05.2f}s`",
                f"  - **Spoken VO Line**: *\"{sc.vo_text}\"*",
                f"  - **Visual State**: Pixel-art characters hold a frozen tableau while the narration text types out on the console in sync with the voiceover and typewriter ticks.",
                f"- **Phase 2 — PIXEL ACTION UNLEASHED (`{sc.still_end:05.2f}s – {sc.end:05.2f}s`)**:",
                f"  - **Action Trigger Cue (`{sc.still_end:05.2f}s`)**: Power fifth stinger + viewport flash transitions badge from `⏸ PIXEL STILL` to `▶ PIXEL ACTION: LIVE 60 FPS`.",
                f"  - **Pixel Action Choreography**: {sc.action_summary}",
                f"  - **Lorekeeper Memory Update**: `{sc.memory_chip}`",
                "",
            ]
        )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return output_path


def render_full_video(
    output_mp4: str = DEFAULT_MP4_PATH,
    contact_sheet_path: str = DEFAULT_CONTACT_SHEET_PATH,
    vo_script_path: str = DEFAULT_VO_SCRIPT_PATH,
) -> None:
    """Synthesize audio, update VO script & contact sheet, and render the 45s 60fps MP4."""
    t0 = time.time()
    print("[1/4] Synthesizing 45.0s procedural soundtrack, SFX, and voiceover in code...")
    pcm16, envelope, vo_meta = generate_full_soundtrack()

    print(f"[2/4] Writing timestamped VO script to {vo_script_path}...")
    write_vo_script(vo_meta, vo_script_path)

    print(f"[3/4] Generating 3-frame contact sheet (8s, 22s, 38s) at {contact_sheet_path}...")
    build_contact_sheet(contact_sheet_path, audio_envelope=envelope)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
        wav_path = tf.name
    save_wav(wav_path, pcm16)

    print(f"[4/4] Rendering {TOTAL_FRAMES} frames at {WIDTH}x{HEIGHT} @ {FPS}fps -> {output_mp4}...")
    ffmpeg_cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "rawvideo",
        "-vcodec",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{WIDTH}x{HEIGHT}",
        "-r",
        str(FPS),
        "-i",
        "-",
        "-i",
        wav_path,
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        "-movflags",
        "+faststart",
        output_mp4,
    ]

    proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE)
    assert proc.stdin is not None
    try:
        for f_idx in range(TOTAL_FRAMES):
            img = render_frame(f_idx, audio_envelope=envelope)
            proc.stdin.write(img.tobytes())
            if (f_idx + 1) % 300 == 0 or (f_idx + 1) == TOTAL_FRAMES:
                elapsed = time.time() - t0
                fps_rate = (f_idx + 1) / max(1e-3, elapsed)
                print(
                    f"      Rendered {f_idx + 1:4d}/{TOTAL_FRAMES} frames "
                    f"({(f_idx + 1) * 100.0 / TOTAL_FRAMES:5.1f}%) — {fps_rate:.1f} fps"
                )
    finally:
        proc.stdin.close()
        ret = proc.wait()
        if os.path.exists(wav_path):
            os.remove(wav_path)
        if ret != 0:
            raise RuntimeError(f"ffmpeg exited with code {ret}")

    total_elapsed = time.time() - t0
    print(f"Done in {total_elapsed:.1f}s! Output saved to: {output_mp4}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Lorekeeper 45s pixel art action video.")
    parser.add_argument(
        "--contact-sheet-only",
        action="store_true",
        help="Only generate the 3-frame contact sheet (8s, 22s, 38s) and VO_SCRIPT.md to check composition.",
    )
    args = parser.parse_args()

    if args.contact_sheet_only:
        pcm16, envelope, vo_meta = generate_full_soundtrack()
        write_vo_script(vo_meta, DEFAULT_VO_SCRIPT_PATH)
        out = build_contact_sheet(DEFAULT_CONTACT_SHEET_PATH, audio_envelope=envelope)
        print(f"Contact sheet generated at: {out}")
    else:
        render_full_video()


if __name__ == "__main__":
    main()
