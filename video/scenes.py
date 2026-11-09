"""
Scene renderer and 1920x1080 motion-graphics compositor for the Lorekeeper
pixel art action video.

Each frame combines:
  1. A true low-resolution pixel-art canvas (340 x 164) rendered with hand-crafted
     16-bit sprites, parallax backgrounds, lighting, and particle physics, then
     upscaled 4x via Nearest-Neighbor to 1360 x 656.
  2. A 1920x1080 motion-graphics UI modelled after Lorekeeper's web interface
     (story log, player move, typewriter narration synchronized with voiceover,
     live audio waveform, hero state sheet, and memory/dreaming badges).
"""

import math
from typing import Dict, List, Optional, Tuple
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from video.config import (
    FPS,
    HEIGHT,
    PIXEL_H,
    PIXEL_SCALE,
    PIXEL_W,
    SCENES,
     TOTAL_DURATION,
    VIEWPORT_X,
    VIEWPORT_Y,
    WIDTH,
    SceneSpec,
    get_scene_at_time,
)
from video.sprites import (
    Color,
    draw_circle,
    draw_dread_wolf,
    draw_garra,
    draw_glow,
    draw_hobb,
    draw_line,
    draw_maren,
    draw_pebble_mule,
    draw_pixel_text,
    draw_sword_slash_arc,
    draw_wren,
    fill_rect,
    put_px,
)


# ============================================================================
# FONT LOADER (Cached for fast 60fps rendering)
# ============================================================================
_FONT_CACHE: Dict[Tuple[str, int], ImageFont.FreeTypeFont] = {}

FONT_PATHS = {
    "serif_bold": "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    "serif": "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    "sans_bold": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "sans": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "mono_bold": "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
    "mono": "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
}


def get_font(style: str, size: int) -> ImageFont.FreeTypeFont:
    key = (style, size)
    if key not in _FONT_CACHE:
        path = FONT_PATHS.get(style, FONT_PATHS["sans"])
        _FONT_CACHE[key] = ImageFont.truetype(path, size)
    return _FONT_CACHE[key]


# ============================================================================
# SCENE 1 PIXEL WORLD: DUSK AT THORNWICK GATE & THE CROOKED LANTERN
# ============================================================================
def render_scene_1_pixel_world(
    canvas: np.ndarray,
    t: float,
    is_action: bool,
    prog: float,
    frame_idx: int,
) -> Tuple[int, int]:
    """Render Scene 1 on the 340x164 pixel canvas. Returns camera (shake_x, shake_y)."""
    h, w, _ = canvas.shape

    # 1. Dusk twilight gradient sky (deep violet -> plum -> warm sunset amber)
    sky_top = np.array([20, 16, 38], dtype=np.float32)
    sky_mid = np.array([54, 30, 68], dtype=np.float32)
    sky_bot = np.array([138, 66, 48], dtype=np.float32)
    horizon_y = 112
    for y in range(horizon_y):
        u = y / horizon_y
        if u < 0.55:
            col = sky_top + (sky_mid - sky_top) * (u / 0.55)
        else:
            col = sky_mid + (sky_bot - sky_mid) * ((u - 0.55) / 0.45)
        # Pixel banding for retro 16-bit gradient feel
        col = np.floor(col / 4.0) * 4.0
        canvas[y, :] = col.astype(np.uint8)

    # Stars & pale dusk crescent moon
    stars = [(28, 16), (64, 24), (105, 12), (148, 28), (195, 15), (242, 22), (310, 18)]
    for idx, (sx, sy) in enumerate(stars):
        twinkle = 255 if (not is_action or (frame_idx + idx * 7) % 24 < 18) else 150
        put_px(canvas, sx, sy, (twinkle, twinkle, 220))
    draw_circle(canvas, 52, 30, 9, (238, 226, 185), fill=True)
    draw_circle(canvas, 55, 28, 8, (34, 22, 48), fill=True)

    # 2. Distant Greywood pine silhouettes along the horizon
    for tx in range(0, w, 11):
        tree_h = 18 + ((tx * 17) % 14)
        base_y = horizon_y
        for row in range(tree_h):
            span = max(1, (row * 6) // tree_h)
            fill_rect(canvas, tx - span, base_y - tree_h + row, span * 2 + 1, 1, (22, 18, 32))

    # 3. Ground & cobblestone village road
    fill_rect(canvas, 0, horizon_y, w, h - horizon_y, (36, 32, 38))
    fill_rect(canvas, 0, 124, w, 40, (54, 48, 52))
    # Cobblestone pattern
    for cy in range(126, 160, 5):
        offset = 4 if ((cy // 5) % 2 == 1) else 0
        for cx in range(offset, w, 10):
            fill_rect(canvas, cx, cy, 8, 3, (74, 66, 70))
            put_px(canvas, cx + 1, cy, (92, 84, 88))

    # 4. Left: Thornwick wooden palisade gate & signpost
    for px_post in range(8, 56, 6):
        fill_rect(canvas, px_post, 78, 5, 46, (68, 44, 30))
        fill_rect(canvas, px_post + 1, 76, 3, 2, (88, 58, 38))
    # Gate arch
    fill_rect(canvas, 58, 66, 6, 58, (82, 52, 34))
    fill_rect(canvas, 92, 66, 6, 58, (82, 52, 34))
    fill_rect(canvas, 54, 64, 48, 6, (104, 68, 44))
    # Gate lantern
    fill_rect(canvas, 66, 74, 3, 4, (255, 195, 70))
    draw_glow(canvas, 67, 76, 14.0, (255, 165, 50), 0.4)

    # Signpost at x=122
    fill_rect(canvas, 122, 98, 3, 26, (90, 58, 38))
    fill_rect(canvas, 112, 101, 24, 6, (132, 88, 54))
    draw_pixel_text(canvas, "INN", 116, 102, (245, 228, 190), shadow=None)

    # 5. Right: The Crooked Lantern Inn (two-story half-timbered tavern)
    inn_x, inn_y = 228, 42
    # Chimney with rising smoke
    fill_rect(canvas, inn_x + 74, inn_y - 12, 10, 24, (78, 68, 72))
    smoke_step = (frame_idx // 3) if is_action else 0
    for s_i in range(4):
        sy = inn_y - 16 - s_i * 5 - (smoke_step % 5 if is_action else 0)
        sx = inn_x + 78 + int(math.sin(s_i + smoke_step * 0.2) * 3)
        draw_circle(canvas, sx, sy, 3 + s_i, (140, 135, 150), fill=True, alpha=0.35)

    # Pitched shingled roof
    for ry in range(26):
        span = 52 + ry * 2
        fill_rect(canvas, inn_x + 48 - span // 2, inn_y + ry, span, 1, (64, 36, 38))
    # Half-timbered walls
    fill_rect(canvas, inn_x, inn_y + 26, 96, 58, (186, 168, 138))
    # Timber framing beams
    for bx in (inn_x, inn_x + 30, inn_x + 62, inn_x + 92):
        fill_rect(canvas, bx, inn_y + 26, 4, 58, (72, 46, 32))
    fill_rect(canvas, inn_x, inn_y + 26, 96, 4, (72, 46, 32))
    fill_rect(canvas, inn_x, inn_y + 54, 96, 4, (72, 46, 32))
    fill_rect(canvas, inn_x - 4, inn_y + 82, 104, 4, (92, 82, 84))

    # Warm glowing tavern windows
    for wx in (inn_x + 10, inn_x + 40, inn_x + 70):
        fill_rect(canvas, wx, inn_y + 34, 14, 14, (255, 195, 75))
        fill_rect(canvas, wx + 2, inn_y + 36, 10, 10, (255, 235, 140))
        fill_rect(canvas, wx + 6, inn_y + 34, 2, 14, (72, 46, 32))
        fill_rect(canvas, wx, inn_y + 40, 14, 2, (72, 46, 32))
        draw_glow(canvas, wx + 7, inn_y + 41, 18.0, (255, 175, 55), 0.35)

    # Tavern door & hanging "Crooked Lantern" sign
    fill_rect(canvas, inn_x + 12, inn_y + 60, 16, 24, (98, 56, 34))
    if is_action:
        # Door opens slightly spilling warm hearth light!
        fill_rect(canvas, inn_x + 14, inn_y + 62, 6, 20, (255, 210, 95))
        draw_glow(canvas, inn_x + 16, inn_y + 72, 22.0, (255, 170, 50), 0.5)

    # Hanging crooked sign bracket on left wall of inn
    draw_line(canvas, inn_x, inn_y + 48, inn_x - 16, inn_y + 48, (40, 36, 42), 2)
    fill_rect(canvas, inn_x - 15, inn_y + 50, 11, 8, (124, 80, 44))
    draw_glow(canvas, inn_x - 10, inn_y + 54, 10.0, (255, 185, 65), 0.35)

    # 6. Characters: STILL vs. ACTION
    if not is_action:
        # STILL PHASE: Completely motionless pixel tableau!
        draw_pebble_mule(canvas, 64, 112, walking=False, frame=0)
        draw_wren(canvas, 94, 112, pose="idle", frame=0, flip_x=False)
        draw_hobb(canvas, 218, 114, active=False, frame=0)
    else:
        # ACTION PHASE: Wren & Pebble stride to the Crooked Lantern; Hobb waves lantern & tosses 3 silver!
        walk_p = min(1.0, prog / 0.48)
        wren_x = 94.0 + walk_p * 78.0  # Walks from 94 -> 172
        pebble_x = 64.0 + walk_p * 74.0
        still_walking = prog < 0.48

        draw_pebble_mule(canvas, pebble_x, 112, walking=still_walking, frame=frame_idx // 4)
        wren_pose = "walk" if still_walking else "salute"
        draw_wren(canvas, wren_x, 112, pose=wren_pose, frame=frame_idx // 3, flip_x=False)
        draw_hobb(canvas, 218, 114, active=True, frame=frame_idx)

        # Three silver coins arcing from Hobb (x=216, y=118) to Wren
        coin_launches = [0.12, 0.22, 0.31]
        for c_idx, c_start in enumerate(coin_launches):
            c_prog = (prog - c_start) / 0.44
            if 0.0 <= c_prog <= 1.0:
                cx = 216.0 + (wren_x + 12.0 - 216.0) * c_prog
                cy = 118.0 - math.sin(c_prog * math.pi) * (24.0 + c_idx * 6.0)
                # Coin sparkle trail
                for tail in range(1, 6):
                    tp = max(0.0, c_prog - tail * 0.045)
                    tx = 216.0 + (wren_x + 12.0 - 216.0) * tp
                    ty = 118.0 - math.sin(tp * math.pi) * (24.0 + c_idx * 6.0)
                    put_px(canvas, tx, ty, (255, 225, 130) if tail % 2 == 0 else (180, 220, 255), alpha=0.75 - tail * 0.12)
                draw_circle(canvas, cx, cy, 3.0, (235, 245, 255), fill=True)
                put_px(canvas, cx, cy, (255, 255, 255))
                draw_glow(canvas, cx, cy, 8.0, (200, 230, 255), 0.65)
            elif c_prog > 1.0 and prog < c_start + 0.72:
                # Catch burst sparkles!
                burst_y = 102 - int((prog - (c_start + 0.44)) * 28) - c_idx * 7
                draw_pixel_text(
                    canvas,
                    "+1 SILVER",
                    int(wren_x) - 8,
                    burst_y,
                    color=(220, 240, 255),
                    shadow=(18, 16, 24),
                )

        if prog >= 0.30:
            banner_y = 74 - int(math.sin(prog * 6.0) * 2)
            fill_rect(canvas, 132, banner_y - 2, 78, 9, (24, 20, 18), alpha=0.84)
            draw_pixel_text(
                canvas,
                "+3 SILVER LENT!",
                136,
                banner_y,
                color=(255, 215, 90),
                shadow=(15, 10, 8),
            )

        # Warm floating tavern embers in the dusk air
        for e_i in range(12):
            ex = 200 + ((e_i * 19 + frame_idx // 2) % 90)
            ey = 122 - ((e_i * 13 + frame_idx) % 55)
            put_px(canvas, ex, ey, (255, 190, 70), alpha=0.75)

    return 0, 0


# ============================================================================
# SCENE 2 PIXEL WORLD: GARRA'S SMITHY FORGE & ELDER MAREN'S SEALED LETTER
# ============================================================================
def render_scene_2_pixel_world(
    canvas: np.ndarray,
    t: float,
    is_action: bool,
    prog: float,
    frame_idx: int,
) -> Tuple[int, int]:
    """Render Scene 2 on the 340x164 pixel canvas. Returns camera (shake_x, shake_y)."""
    h, w, _ = canvas.shape
    shake_x, shake_y = 0, 0

    # 1. Stone Smithy interior background
    fill_rect(canvas, 0, 0, w, 122, (32, 26, 28))
    # Stone brick wall courses
    for by in range(10, 120, 10):
        offset = 8 if ((by // 10) % 2 == 1) else 0
        for bx in range(offset, w, 18):
            fill_rect(canvas, bx, by, 16, 8, (44, 36, 38))
            put_px(canvas, bx + 1, by + 1, (56, 46, 48))

    # Timber ceiling beams & pillars
    fill_rect(canvas, 0, 0, w, 10, (54, 36, 24))
    for px_col in (16, 128, 318):
        fill_rect(canvas, px_col, 10, 8, 114, (58, 38, 26))

    # Smithy flagstone floor
    fill_rect(canvas, 0, 122, w, h - 122, (46, 40, 42))
    for fx in range(0, w, 16):
        fill_rect(canvas, fx, 124, 14, 6, (62, 54, 56))
        fill_rect(canvas, fx + 4, 132, 14, 8, (54, 46, 48))

    # 2. Left side: Arched window looking out onto Thornwick morning + Elder Maren's alcove
    fill_rect(canvas, 36, 28, 48, 56, (72, 108, 138))
    fill_rect(canvas, 40, 32, 40, 48, (118, 162, 190))
    # Window mullions
    fill_rect(canvas, 59, 28, 2, 56, (44, 34, 28))
    fill_rect(canvas, 36, 54, 48, 2, (44, 34, 28))
    draw_glow(canvas, 60, 56, 28.0, (160, 200, 230), 0.22)

    # Weapon rack in center background
    fill_rect(canvas, 146, 44, 46, 36, (62, 40, 28))
    fill_rect(canvas, 144, 42, 50, 4, (86, 56, 38))
    for wx in (154, 168, 182):
        draw_line(canvas, wx, 48, wx, 74, (185, 198, 215), 2)
        fill_rect(canvas, wx - 2, 54, 5, 2, (218, 170, 70))

    # 3. Right side: Roaring Brick Forge & Anvil
    forge_x = 258
    fill_rect(canvas, forge_x, 22, 58, 100, (66, 44, 40))
    fill_rect(canvas, forge_x - 4, 52, 66, 8, (88, 58, 52))
    # Forge fire opening
    fill_rect(canvas, forge_x + 10, 68, 38, 36, (22, 14, 14))
    flicker = int(math.sin(frame_idx * 0.4) * 3) if is_action else 0
    fill_rect(canvas, forge_x + 12, 78 - flicker, 34, 24 + flicker, (225, 72, 24))
    fill_rect(canvas, forge_x + 16, 84 - flicker, 26, 18 + flicker, (255, 158, 36))
    fill_rect(canvas, forge_x + 22, 90 - flicker, 14, 12 + flicker, (255, 242, 150))
    draw_glow(canvas, forge_x + 29, 88, 42.0 + flicker * 2, (255, 125, 35), 0.55)

    # Heavy Iron Anvil at x=212, y=114
    anvil_x, anvil_y = 210, 114
    fill_rect(canvas, anvil_x + 2, anvil_y + 6, 14, 8, (72, 48, 32))  # Timber block base
    fill_rect(canvas, anvil_x - 4, anvil_y, 24, 6, (108, 116, 130))  # Anvil body
    fill_rect(canvas, anvil_x - 9, anvil_y + 1, 6, 3, (128, 138, 154))  # Anvil horn
    fill_rect(canvas, anvil_x - 4, anvil_y, 22, 2, (162, 174, 192))  # Polished top face

    # 4. Characters & Action Sequence
    if not is_action:
        # STILL PHASE: Frozen tableau!
        # Glowing orange blade resting on anvil
        fill_rect(canvas, anvil_x - 2, anvil_y - 2, 12, 2, (255, 165, 50))
        draw_maren(canvas, 76, 104, seal_broken=False, frame=0)
        draw_wren(canvas, 142, 106, pose="idle", frame=0, flip_x=False)
        draw_garra(canvas, 222, 102, hammer_phase=0.0, is_action=False)
    else:
        # ACTION PHASE:
        # Sub-phase A (prog 0.0 -> 0.56): Garra slams hammer 4 times in showers of sparks;
        # Maren breaks seal & blesses the blue glass bead!
        # Sub-phase B (prog 0.56 -> 1.0): Garra tosses honed blade; Wren catches & unleashes
        # a blazing golden crescent slash (including t = 22.0s -> prog = 0.60)!
        strike_cycles = (prog / 0.14)
        hammer_phase = strike_cycles % 1.0 if prog < 0.58 else 0.2

        # Check if hammer just struck anvil for camera shake & sparks
        is_impact = (prog < 0.58 and 0.42 <= hammer_phase <= 0.68) or (0.58 <= prog <= 0.72)
        if is_impact:
            shake_x = int(math.sin(frame_idx * 1.9) * 2)
            shake_y = int(math.cos(frame_idx * 2.3) * 2)

        draw_maren(canvas, 76, 104, seal_broken=True, frame=frame_idx)
        # Golden memory runes rising from Maren's opened letter
        for r_i in range(4):
            ry = 104 - ((frame_idx // 2 + r_i * 9) % 32)
            rx = 88 + int(math.sin(r_i * 2.0 + frame_idx * 0.12) * 5)
            fill_rect(canvas, rx, ry, 2, 3, (255, 220, 110), alpha=0.8)

        # Glowing cyan blessing arc from Maren's blue glass bead to Wren
        bead_prog = min(1.0, prog * 1.8)
        bx = 90 + (150 - 90) * bead_prog
        by = 108 - math.sin(bead_prog * math.pi) * 18
        draw_circle(canvas, bx, by, 3, (90, 235, 255), fill=True)
        draw_glow(canvas, bx, by, 10.0, (70, 220, 255), 0.55)

        draw_garra(canvas, 222, 102, hammer_phase=hammer_phase, is_action=True)

        # Anvil sparks fountain (continues shimmering through the blade slash!)
        num_sparks = 38
        for s_i in range(num_sparks):
            seed = s_i * 37.17
            age = ((frame_idx * 0.045 + s_i * 0.11) % 1.0)
            ang = -math.pi * (0.15 + 0.70 * ((s_i * 13) % 100) / 100.0)
            spd = 18.0 + ((s_i * 29) % 28)
            sx = anvil_x + 4 + math.cos(ang) * spd * age
            sy = anvil_y - 1 + math.sin(ang) * spd * age + 28.0 * (age ** 2)
            s_col = (255, 250, 190) if age < 0.35 else ((255, 175, 45) if age < 0.7 else (220, 75, 25))
            put_px(canvas, sx, sy, s_col)

        if prog < 0.52:
            # Blade still on anvil being forged white-hot
            fill_rect(canvas, anvil_x - 2, anvil_y - 2, 12, 2, (255, 235, 140))
            draw_glow(canvas, anvil_x + 4, anvil_y - 2, 14.0, (255, 180, 50), 0.65)
            draw_wren(canvas, 146, 106, pose="combat_ready", frame=frame_idx, flip_x=False)
        else:
            # Wren catches the newly tempered short sword and unleashes a blazing golden slash!
            draw_wren(canvas, 152, 104, pose="catch_slash", frame=frame_idx, flip_x=False)
            draw_sword_slash_arc(
                canvas,
                cx=164,
                cy=108,
                radius=24.0,
                angle_start_deg=-75.0,
                angle_end_deg=65.0,
                color_outer=(255, 195, 55),
                color_inner=(255, 252, 215),
                thickness=4,
            )
            draw_glow(canvas, 176, 104, 24.0, (255, 200, 70), 0.55)
            # Floating pixel banner
            fill_rect(canvas, 112, 66, 126, 9, (22, 18, 16), alpha=0.85)
            draw_pixel_text(
                canvas,
                "BLADE HONED! +WOLF PACT",
                116,
                68,
                color=(255, 222, 95),
                shadow=(15, 10, 8),
            )

    return shake_x, shake_y


# ============================================================================
# SCENE 3 PIXEL WORLD: MOONRISE IN THE GREYWOOD — BATTLE AT THE OLD MILL
# ============================================================================
def render_scene_3_pixel_world(
    canvas: np.ndarray,
    t: float,
    is_action: bool,
    prog: float,
    frame_idx: int,
) -> Tuple[int, int]:
    """Render Scene 3 on the 340x164 pixel canvas. Returns camera (shake_x, shake_y)."""
    h, w, _ = canvas.shape
    shake_x, shake_y = 0, 0

    # 1. Night sky in the Greywood
    sky_top = np.array([10, 14, 26], dtype=np.float32)
    sky_bot = np.array([28, 36, 56], dtype=np.float32)
    horizon_y = 114
    for y in range(horizon_y):
        u = y / horizon_y
        col = np.floor((sky_top + (sky_bot - sky_top) * u) / 3.0) * 3.0
        canvas[y, :] = col.astype(np.uint8)

    # Giant Full Moon (blood-silver) hanging over the Greywood at center-right
    moon_x, moon_y = 186, 42
    draw_glow(canvas, moon_x, moon_y, 44.0, (185, 205, 240), 0.38)
    draw_circle(canvas, moon_x, moon_y, 24, (226, 232, 245), fill=True)
    draw_circle(canvas, moon_x - 6, moon_y - 4, 5, (196, 206, 226), fill=True)
    draw_circle(canvas, moon_x + 7, moon_y + 6, 4, (196, 206, 226), fill=True)

    # 2. Parallax gnarled Greywood trees
    for tx in range(10, w, 22):
        # Leave an opening around the giant moon for silhouette drama
        tree_h = 56 if abs(tx - moon_x) > 34 else 32
        fill_rect(canvas, tx, horizon_y - tree_h, 5, tree_h, (18, 22, 34))
        # Jagged canopy branches
        for b in range(3):
            by = horizon_y - tree_h + b * 10
            span = 10 + b * 4
            fill_rect(canvas, tx + 2 - span, by, span * 2, 5, (16, 26, 36))

    # Glowing red eyes of unseen creatures in the deep brush
    for ex in (96, 138, 298, 322):
        if not is_action or (frame_idx + ex) % 40 < 32:
            put_px(canvas, ex, 104, (255, 45, 65))
            put_px(canvas, ex + 2, 104, (255, 45, 65))

    # 3. Left: The Old Mill & Waterwheel
    mill_x = 8
    fill_rect(canvas, mill_x, 54, 48, 62, (46, 44, 54))
    for ry in range(18):
        fill_rect(canvas, mill_x - 4 + ry, 36 + ry, 56 - ry * 2, 1, (36, 28, 32))
    # Wooden waterwheel
    wheel_cx, wheel_cy = 56, 98
    draw_circle(canvas, wheel_cx, wheel_cy, 15, (92, 62, 40), fill=False)
    draw_circle(canvas, wheel_cx, wheel_cy, 4, (120, 82, 54), fill=True)
    wheel_ang_offset = (frame_idx * 2.5) if is_action else 0.0
    for spoke in range(6):
        ang = math.radians(spoke * 60.0 + wheel_ang_offset)
        sx = wheel_cx + math.cos(ang) * 14
        sy = wheel_cy + math.sin(ang) * 14
        draw_line(canvas, wheel_cx, wheel_cy, sx, sy, (92, 62, 40), 1)

    # 4. Forest floor & shimmering Millstream
    fill_rect(canvas, 0, horizon_y, w, h - horizon_y, (22, 28, 36))
    # Millstream running from the waterwheel across the foreground
    fill_rect(canvas, 44, 124, 96, 22, (34, 68, 98))
    for wy in range(126, 144, 4):
        shim = (frame_idx // 2 if is_action else 0) % 12
        for wx in range(48 + shim, 134, 14):
            fill_rect(canvas, wx, wy, 6, 1, (110, 185, 225))

    # Mossy banks & rocks
    fill_rect(canvas, 134, 120, 206, 36, (30, 38, 44))
    fill_rect(canvas, 240, 112, 44, 12, (48, 54, 66))

    # Eerie ground mist
    for mx in range(0, w, 28):
        m_shift = int(math.sin(mx * 0.1 + (frame_idx * 0.05 if is_action else 0)) * 4)
        fill_rect(canvas, mx + m_shift, 115, 20, 3, (120, 140, 165), alpha=0.22)

    # 5. Combat Choreography: STILL vs. ACTION
    if not is_action:
        # STILL PHASE: Frozen standoff before the ambush!
        draw_wren(canvas, 96, 108, pose="combat_ready", frame=0, flip_x=False)
        draw_dread_wolf(canvas, 244, 100, pose="still", frame=0)
    else:
        # ACTION PHASE (31.0s -> 39.5s, duration 8.5s):
        # Notice at t = 38.0s, prog = (38.0 - 31.0) / 8.5 = 0.8235!
        if prog < 0.32:
            # Beat 1: Dread-Wolf lunges across the millstream; Wren parries with blue glass bead ward!
            sub = prog / 0.32
            wolf_x = 244.0 - math.sin(sub * math.pi * 0.75) * 112.0
            wren_x = 96.0 - math.sin(sub * math.pi * 0.5) * 10.0
            draw_wren(canvas, wren_x, 108, pose="parry", frame=frame_idx, flip_x=False)
            draw_dread_wolf(canvas, wolf_x, 100, pose="lunge", frame=frame_idx)
            if 0.35 <= sub <= 0.85:
                shake_x = int(math.sin(frame_idx * 2.2) * 3)
                # Ward impact sparks & water splash!
                for sp in range(20):
                    ang = sp * (2 * math.pi / 20)
                    r = (sub - 0.35) * 36.0
                    put_px(canvas, wren_x + 18 + math.cos(ang) * r, 112 + math.sin(ang) * r, (100, 240, 255))
                draw_pixel_text(canvas, "WARD PARRY! -3 HP", int(wren_x) - 8, 86, (110, 240, 255))

        elif prog < 0.64:
            # Beat 2: Wren counter-dashes with cyan afterimages & twin golden slashes!
            sub = (prog - 0.32) / 0.32
            wren_x = 86.0 + sub * 86.0
            wolf_x = 166.0 + sub * 28.0
            # Draw 3 cyan/emerald dash afterimages behind Wren
            for ghost in range(3, 0, -1):
                gx = wren_x - ghost * 12
                draw_wren(
                    canvas,
                    gx,
                    108,
                    pose="dash_slash",
                    frame=frame_idx,
                    afterimage_tint=(65, 220, 245),
                    alpha=0.22 * (4 - ghost) / 3.0,
                )
            draw_wren(canvas, wren_x, 108, pose="dash_slash", frame=frame_idx, flip_x=False)
            draw_dread_wolf(canvas, wolf_x, 102, pose="recoil", frame=frame_idx)
            draw_sword_slash_arc(
                canvas,
                cx=wren_x + 14,
                cy=112,
                radius=22.0,
                angle_start_deg=-60,
                angle_end_deg=70,
                color_outer=(255, 200, 65),
                color_inner=(255, 255, 230),
                thickness=3,
            )
            shake_x = int(math.sin(frame_idx * 2.0) * 2)
            draw_pixel_text(canvas, "COMBO SLASH! -6 HP", int(wolf_x) - 10, 82, (255, 215, 85))

        else:
            # Beat 3 (prog 0.64 -> 1.0, including t = 38.0s at prog = 0.8235!):
            # CLIMAX MOONLIT CLEAVE! Wren leaps high in front of the full moon, slicing a massive
            # golden-cyan crescent arc across the Dread-Wolf in a burst of sparks + "+1 WOLF PELT"!
            sub = (prog - 0.64) / 0.36  # at t=38.0s, sub = 0.51 (exact apex of the leap!)
            leap_arc = math.sin(min(1.0, sub * 1.15) * math.pi)
            wren_x = 164.0 + sub * 24.0
            wren_y = 106.0 - leap_arc * 34.0  # Apex right in front of the giant moon!
            wolf_x = 196.0 + sub * 10.0
            wolf_y = 100.0 - leap_arc * 12.0

            if sub < 0.72:
                shake_x = int(math.sin(frame_idx * 2.5) * 3)
                shake_y = int(math.cos(frame_idx * 2.1) * 2)

            # Afterimage trail up toward the moon
            for ghost in range(2, 0, -1):
                draw_wren(
                    canvas,
                    wren_x - ghost * 8,
                    wren_y + ghost * 7,
                    pose="leap_cleave",
                    frame=frame_idx,
                    afterimage_tint=(95, 235, 255),
                    alpha=0.30,
                )

            # Dread-Wolf taking the decisive cleave
            wolf_pose = "lunge" if sub < 0.78 else "cleaved"
            draw_dread_wolf(canvas, wolf_x, wolf_y, pose=wolf_pose, frame=int((sub - 0.78) * 60) if sub >= 0.78 else frame_idx)

            # Wren airborne delivering the Moon Cleave
            draw_wren(canvas, wren_x, wren_y, pose="leap_cleave", frame=frame_idx, flip_x=False)

            # Massive dual-layer Golden + Cyan Moon Cleave Crescent!
            draw_sword_slash_arc(
                canvas,
                cx=wren_x + 14,
                cy=wren_y + 10,
                radius=34.0,
                angle_start_deg=-85.0,
                angle_end_deg=85.0,
                color_outer=(75, 235, 255),
                color_inner=(255, 255, 255),
                thickness=5,
            )
            draw_sword_slash_arc(
                canvas,
                cx=wren_x + 16,
                cy=wren_y + 10,
                radius=28.0,
                angle_start_deg=-75.0,
                angle_end_deg=75.0,
                color_outer=(255, 200, 55),
                color_inner=(255, 252, 210),
                thickness=4,
            )
            draw_glow(canvas, wolf_x + 8, wolf_y + 8, 32.0, (255, 215, 90), 0.65)

            # Explosive hit sparks radiating from the cleave impact
            for s_i in range(48):
                ang = s_i * (2.0 * math.pi / 48.0) + (s_i % 3) * 0.2
                dist = 6.0 + ((s_i * 17) % 28) * min(1.2, sub * 1.6)
                sx = wolf_x + 10 + math.cos(ang) * dist
                sy = wolf_y + 8 + math.sin(ang) * dist * 0.75
                col = (255, 235, 110) if (s_i % 3 == 0) else ((90, 240, 255) if (s_i % 3 == 1) else (255, 75, 95))
                fill_rect(canvas, int(sx), int(sy), 2, 2, col)

            # Floating RPG Critical Hit & Quest Item Loot Banner!
            fill_rect(canvas, 134, 48, 132, 18, (18, 14, 22), alpha=0.88)
            draw_pixel_text(canvas, "CRIT! -15 HP", 142, 50, (255, 95, 95))
            draw_pixel_text(canvas, "+1 WOLF PELT FOR GARRA", 142, 58, (255, 225, 95))

    return shake_x, shake_y


# ============================================================================
# SCENE 4 PIXEL WORLD: OFFLINE DREAMING & CANON REBUILT AT DAWN RIDGE
# ============================================================================
def render_scene_4_pixel_world(
    canvas: np.ndarray,
    t: float,
    is_action: bool,
    prog: float,
    frame_idx: int,
) -> Tuple[int, int]:
    """Render Scene 4 on the 340x164 pixel canvas. Returns camera (shake_x, shake_y)."""
    h, w, _ = canvas.shape

    # 1. Dawn sunrise gradient sky (deep indigo -> rose-violet -> golden dawn)
    dawn_boost = (prog * 0.35) if is_action else 0.0
    sky_top = np.array([18, 20, 44], dtype=np.float32)
    sky_mid = np.array([92, 48, 84], dtype=np.float32) * (1.0 + dawn_boost)
    sky_bot = np.array([224, 138, 68], dtype=np.float32) * (1.0 + dawn_boost * 0.6)
    horizon_y = 118
    for y in range(horizon_y):
        u = y / horizon_y
        if u < 0.55:
            col = sky_top + (sky_mid - sky_top) * (u / 0.55)
        else:
            col = sky_mid + (sky_bot - sky_mid) * ((u - 0.55) / 0.45)
        col = np.clip(np.floor(col / 4.0) * 4.0, 0, 255)
        canvas[y, :] = col.astype(np.uint8)

    # Rising golden sun on the horizon
    sun_y = int(112 - (prog * 14 if is_action else 0))
    draw_glow(canvas, 240, sun_y, 48.0, (255, 190, 80), 0.55)
    draw_circle(canvas, 240, sun_y, 18, (255, 232, 135), fill=True)

    # Distant silhouette of Thornwick village & Greywood below the ridge
    fill_rect(canvas, 0, 110, w, 12, (36, 26, 42))
    # Tiny distant roofs of the Crooked Lantern & Chapel
    fill_rect(canvas, 188, 103, 16, 8, (46, 32, 48))
    fill_rect(canvas, 212, 100, 12, 11, (46, 32, 48))

    # Foreground rocky overlook ridge
    fill_rect(canvas, 0, 120, w, 44, (44, 38, 46))
    fill_rect(canvas, 20, 116, 175, 10, (64, 54, 62))
    fill_rect(canvas, 24, 116, 165, 2, (96, 82, 88))

    # Campfire at x=138, y=114
    fill_rect(canvas, 134, 115, 10, 3, (92, 56, 34))
    flick = (frame_idx % 4) if is_action else 0
    fill_rect(canvas, 136, 109 - flick, 6, 6 + flick, (255, 140, 35))
    fill_rect(canvas, 137, 111 - flick, 4, 4 + flick, (255, 235, 120))
    draw_glow(canvas, 139, 112, 22.0, (255, 165, 55), 0.45)

    # Characters on the ridge
    draw_pebble_mule(canvas, 58, 102, walking=False, frame=0)
    if not is_action:
        # STILL PHASE: Wren stands motionless with the silver wolf pelt draped over shoulders
        draw_wren(canvas, 98, 102, pose="idle", frame=0, flip_x=False, has_wolf_pelt=True)
    else:
        # ACTION PHASE: Wren raises short sword to the dawn as Golden Memory Constellations
        # form in the sky and rebuild canon.md!
        draw_wren(canvas, 98, 102, pose="victory", frame=frame_idx, flip_x=False, has_wolf_pelt=True)

        nodes = [
            (72, 48, "HOBB: 3 SILVER"),
            (142, 30, "GARRA: WOLF PELT"),
            (218, 44, "MAREN: LETTER"),
            (142, 68, "CANON.MD REBUILT"),
        ]
        # Connect memory constellation lines
        for i in range(len(nodes)):
            nx0, ny0, _ = nodes[i]
            nx1, ny1, _ = nodes[(i + 1) % len(nodes)]
            draw_line(canvas, nx0, ny0, nx1, ny1, (255, 215, 95), 1, alpha=min(1.0, prog * 1.6))

        for nx, ny, label in nodes:
            draw_glow(canvas, nx, ny, 12.0, (255, 210, 80), 0.5)
            draw_circle(canvas, nx, ny, 3, (255, 250, 200), fill=True)
            draw_pixel_text(canvas, label, nx - len(label) * 2, ny - 9, (255, 238, 165))

    return 0, 0


# ============================================================================
# FULL 1920x1080 MOTION-GRAPHICS COMPOSITOR (LOREKEEPER UI + PIXEL VIEWPORT)
# ============================================================================
def render_frame(frame_idx: int, audio_envelope: Optional[np.ndarray] = None) -> Image.Image:
    """
    Render a single 1920x1080 RGB frame at `frame_idx` (0 .. TOTAL_FRAMES - 1).
    """
    t = frame_idx / float(FPS)
    scene, is_action, prog = get_scene_at_time(t)

    # 1. Render the low-res 340x164 Pixel Art World Canvas
    px_canvas = np.zeros((PIXEL_H, PIXEL_W, 3), dtype=np.uint8)
    if scene.scene_id == 1:
        shake_x, shake_y = render_scene_1_pixel_world(px_canvas, t, is_action, prog, frame_idx)
    elif scene.scene_id == 2:
        shake_x, shake_y = render_scene_2_pixel_world(px_canvas, t, is_action, prog, frame_idx)
    elif scene.scene_id == 3:
        shake_x, shake_y = render_scene_3_pixel_world(px_canvas, t, is_action, prog, frame_idx)
    else:
        shake_x, shake_y = render_scene_4_pixel_world(px_canvas, t, is_action, prog, frame_idx)

    # Apply camera shake on pixel canvas if active
    if shake_x != 0 or shake_y != 0:
        px_canvas = np.roll(px_canvas, shift=(shake_y, shake_x), axis=(0, 1))

    # Subtle retro scanline shading on every 4th upscaled row after integer 4x Nearest-Neighbor upscale
    upscaled = np.repeat(np.repeat(px_canvas, PIXEL_SCALE, axis=0), PIXEL_SCALE, axis=1)
    upscaled[3::4, :, :] = (upscaled[3::4, :, :].astype(np.uint16) * 88 // 100).astype(np.uint8)

    # Flash border/glint right when STILL transitions to ACTION!
    action_flash = 0.0
    if is_action and (t - scene.still_end) < 0.35:
        action_flash = max(0.0, 1.0 - (t - scene.still_end) / 0.35)
        upscaled = np.clip(
            upscaled.astype(np.float32) + action_flash * 55.0, 0, 255
        ).astype(np.uint8)

    # 2. Create 1920x1080 base frame matching Lorekeeper's dark parchment theme
    frame = Image.new("RGB", (WIDTH, HEIGHT), (21, 19, 15))
    draw = ImageDraw.Draw(frame)

    # Paste the 1360x656 integer-scaled pixel art viewport
    vp_w = PIXEL_W * PIXEL_SCALE  # 1360
    vp_h = PIXEL_H * PIXEL_SCALE  # 656
    frame.paste(Image.fromarray(upscaled), (VIEWPORT_X, VIEWPORT_Y))

    # Viewport frame border (amber in STILL mode, glowing emerald/gold in ACTION mode)
    border_col = (95, 225, 145) if is_action else (217, 165, 74)
    if action_flash > 0.1:
        border_col = (255, 245, 190)
    draw.rectangle(
        [VIEWPORT_X - 2, VIEWPORT_Y - 2, VIEWPORT_X + vp_w + 2, VIEWPORT_Y + vp_h + 2],
        outline=border_col,
        width=3,
    )

    # Top-left overlay badge inside pixel viewport showing STILL vs ACTION state clearly
    badge_bg = (24, 52, 36) if is_action else (44, 34, 22)
    draw.rounded_rectangle(
        [VIEWPORT_X + 16, VIEWPORT_Y + 14, VIEWPORT_X + 450, VIEWPORT_Y + 52],
        radius=6,
        fill=badge_bg,
        outline=border_col,
        width=2,
    )
    mode_label = (
        "▶ PIXEL ACTION: LIVE 60 FPS"
        if is_action
        else "⏸ PIXEL STILL: VOICEOVER READING TEXT"
    )
    draw.text(
        (VIEWPORT_X + 28, VIEWPORT_Y + 23),
        mode_label,
        font=get_font("mono_bold", 17),
        fill=(255, 245, 215) if is_action else (240, 195, 105),
    )

    # Top-right turn & location badge inside viewport
    draw.rounded_rectangle(
        [VIEWPORT_X + vp_w - 420, VIEWPORT_Y + 14, VIEWPORT_X + vp_w - 16, VIEWPORT_Y + 52],
        radius=6,
        fill=(28, 24, 19),
        outline=(74, 64, 50),
        width=1,
    )
    draw.text(
        (VIEWPORT_X + vp_w - 404, VIEWPORT_Y + 23),
        f"{scene.turn_id}  •  {scene.location}",
        font=get_font("mono", 15),
        fill=(210, 198, 176),
    )

    # ========================================================================
    # 3. TOP HEADER BAR (0 .. 68)
    # ========================================================================
    draw.rectangle([0, 0, WIDTH, 68], fill=(30, 27, 22))
    draw.line([(0, 68), (WIDTH, 68)], fill=(58, 52, 42), width=2)

    draw.text(
        (40, 18),
        "LOREKEEPER",
        font=get_font("serif_bold", 26),
        fill=(217, 165, 74),
    )
    draw.text(
        (235, 23),
        f"//  {scene.title}",
        font=get_font("mono_bold", 18),
        fill=(236, 228, 212),
    )

    # Right header: Timecode & Frame counter
    tc_text = f"T+{t:05.2f}s / 45.00s   |   FRAME {frame_idx + 1:04d}/2700   |   1920x1080 @ 60FPS"
    draw.text(
        (WIDTH - 640, 24),
        tc_text,
        font=get_font("mono", 15),
        fill=(168, 156, 134),
    )

    # ========================================================================
    # 4. RIGHT SIDEBAR: HERO STATE SHEET & AGENT MEMORY (x: 1424 .. 1880)
    # ========================================================================
    sb_x0, sb_y0, sb_x1, sb_y1 = 1424, VIEWPORT_Y, 1880, VIEWPORT_Y + vp_h
    draw.rounded_rectangle(
        [sb_x0, sb_y0, sb_x1, sb_y1],
        radius=8,
        fill=(30, 27, 22),
        outline=(58, 52, 42),
        width=2,
    )

    # Sidebar Fake Tabs (State | Notes | Wiki | Canon)
    tabs = ["State", "Notes", "Wiki", "Canon"]
    tab_w = (sb_x1 - sb_x0) // 4
    active_tab = 3 if scene.scene_id == 4 else (1 if is_action else 0)
    for idx, t_name in enumerate(tabs):
        tx0 = sb_x0 + idx * tab_w
        tx1 = tx0 + tab_w
        is_sel = idx == active_tab
        draw.text(
            (tx0 + 28, sb_y0 + 14),
            t_name,
            font=get_font("sans_bold" if is_sel else "sans", 15),
            fill=(236, 228, 212) if is_sel else (140, 128, 110),
        )
        if is_sel:
            draw.line([(tx0 + 8, sb_y0 + 42), (tx1 - 8, sb_y0 + 42)], fill=(217, 165, 74), width=3)
    draw.line([(sb_x0, sb_y0 + 44), (sb_x1, sb_y0 + 44)], fill=(58, 52, 42), width=1)

    # Hero Name & Animated HP Bar
    cur_hp = scene.hp_end if (is_action and prog > 0.35) else scene.hp_start
    cur_copper = scene.copper_end if (is_action and prog > 0.35) else scene.copper_start
    silver_val = cur_copper // 100

    draw.text((sb_x0 + 22, sb_y0 + 60), "Wren", font=get_font("serif_bold", 26), fill=(236, 228, 212))
    draw.text(
        (sb_x0 + 110, sb_y0 + 67),
        "HERO OF SALTMERE",
        font=get_font("mono", 13),
        fill=(140, 128, 110),
    )

    # HP Bar
    draw.text((sb_x0 + 22, sb_y0 + 102), f"HP  {cur_hp}/12", font=get_font("mono_bold", 15), fill=(143, 191, 122))
    bar_x0, bar_y0, bar_w, bar_h = sb_x0 + 120, sb_y0 + 105, 310, 12
    draw.rounded_rectangle([bar_x0, bar_y0, bar_x0 + bar_w, bar_y0 + bar_h], radius=5, fill=(44, 38, 30))
    hp_fill_w = int(bar_w * (cur_hp / 12.0))
    hp_col = (143, 191, 122) if cur_hp >= 10 else (217, 179, 74)
    draw.rounded_rectangle([bar_x0, bar_y0, bar_x0 + hp_fill_w, bar_y0 + bar_h], radius=5, fill=hp_col)

    # Purse & Location
    draw.text((sb_x0 + 22, sb_y0 + 132), "Purse:", font=get_font("sans", 15), fill=(168, 156, 134))
    draw.text(
        (sb_x0 + 120, sb_y0 + 132),
        f"{silver_val} silver ({cur_copper} copper)",
        font=get_font("mono_bold", 15),
        fill=(217, 165, 74),
    )

    # Inventory Section
    draw.line([(sb_x0 + 18, sb_y0 + 166), (sb_x1 - 18, sb_y0 + 166)], fill=(58, 52, 42), width=1)
    draw.text((sb_x0 + 22, sb_y0 + 178), "INVENTORY & EQUIPMENT", font=get_font("mono_bold", 13), fill=(122, 111, 93))

    inv_items = [
        ("traveling cloak", scene.scene_id == 1),
        ("short sword (Garra-honed)" if scene.scene_id >= 2 else "short sword", scene.scene_id in (2, 3)),
        ("sealed letter for Maren", scene.scene_id in (1, 2)),
        ("blue glass bead (mother's charm)", scene.scene_id in (2, 3)),
    ]
    if scene.scene_id > 3 or (scene.scene_id == 3 and is_action and prog >= 0.68):
        inv_items.append(("greywood wolf pelt [NEW]", True))

    for i_idx, (item_name, highlighted) in enumerate(inv_items):
        iy = sb_y0 + 206 + i_idx * 30
        bullet = "▸ " if highlighted else "• "
        col = (255, 220, 115) if highlighted else (210, 200, 182)
        draw.text((sb_x0 + 24, iy), bullet + item_name, font=get_font("mono", 14), fill=col)

    # Layered Agent Memory & Dreaming Section
    mem_top = sb_y0 + 372
    draw.line([(sb_x0 + 18, mem_top), (sb_x1 - 18, mem_top)], fill=(58, 52, 42), width=1)
    draw.text(
        (sb_x0 + 22, mem_top + 14),
        "AGENT MEMORY  •  NOTES & WIKI",
        font=get_font("mono_bold", 13),
        fill=(217, 165, 74),
    )

    memory_notes = [
        ("n0001", "Grew up in Saltmere on the coast", "CONFIRMED", 1),
        ("n0002", "Owes Hobb 3 silver by full moon", "CONFIRMED" if scene.scene_id == 4 else "UNVERIFIED", 1),
        ("n0003", "Promised Garra a Greywood wolf pelt", "CONFIRMED" if scene.scene_id >= 3 else "UNVERIFIED", 2),
        ("n0004", "Elder Maren read the sealed letter", "CONFIRMED" if scene.scene_id >= 3 else "UNVERIFIED", 2),
    ]

    for n_idx, (nid, ntext, status, min_scene) in enumerate(memory_notes):
        ny = mem_top + 44 + n_idx * 58
        visible = scene.scene_id > min_scene or (scene.scene_id == min_scene and (is_action or prog > 0.5))
        box_fill = (38, 34, 27) if visible else (26, 23, 18)
        draw.rounded_rectangle(
            [sb_x0 + 20, ny, sb_x1 - 20, ny + 48],
            radius=6,
            fill=box_fill,
            outline=(78, 68, 52) if visible else (44, 38, 30),
        )
        badge_col = (143, 191, 122) if status == "CONFIRMED" else (217, 179, 74)
        draw.text(
            (sb_x0 + 30, ny + 8),
            f"[{status}] {nid}",
            font=get_font("mono_bold", 12),
            fill=badge_col if visible else (90, 82, 70),
        )
        draw.text(
            (sb_x0 + 30, ny + 26),
            ntext if visible else "Awaiting campaign turn...",
            font=get_font("sans", 13),
            fill=(230, 220, 204) if visible else (100, 92, 78),
        )

    # ========================================================================
    # 5. BOTTOM CAMPAIGN TEXT & VOICEOVER CONSOLE (y: 758 .. 1048)
    # ========================================================================
    con_x0, con_y0, con_x1, con_y1 = 40, 758, 1880, 1048
    draw.rounded_rectangle(
        [con_x0, con_y0, con_x1, con_y1],
        radius=10,
        fill=(30, 27, 22),
        outline=(74, 64, 50),
        width=2,
    )

    # Left column of console: Campaign Turn Log (Player Move + VO Narration)
    draw.text(
        (con_x0 + 28, con_y0 + 20),
        "PLAYER MOVE  ",
        font=get_font("mono_bold", 14),
        fill=(122, 111, 93),
    )
    draw.text(
        (con_x0 + 150, con_y0 + 18),
        f"> {scene.player_move}",
        font=get_font("mono_bold", 18),
        fill=(156, 195, 217),
    )

    draw.line([(con_x0 + 28, con_y0 + 54), (con_x1 - 28, con_y0 + 54)], fill=(52, 46, 38), width=1)

    # Typewriter reveal of Game Master Narration during STILL phase (100% revealed during ACTION phase)
    full_vo = scene.vo_text
    if not is_action:
        # Typewriter progresses smoothly across the STILL phase
        char_fraction = min(1.0, max(0.0, (t - scene.vo_start) / max(0.5, (scene.still_end - scene.vo_start - 0.35))))
        n_chars = int(round(len(full_vo) * char_fraction))
        shown_vo = full_vo[:n_chars]
        cursor = " █" if (frame_idx // 8) % 2 == 0 else ""
    else:
        shown_vo = full_vo
        cursor = ""

    draw.text(
        (con_x0 + 28, con_y0 + 70),
        "GAME MASTER NARRATION (VOICEOVER):",
        font=get_font("mono_bold", 14),
        fill=(217, 165, 74),
    )
    draw.text(
        (con_x0 + 28, con_y0 + 98),
        f"“{shown_vo}{cursor}”",
        font=get_font("serif_bold", 20),
        fill=(236, 228, 212),
    )

    # Memory / Action Status Chip Row inside console
    chip_y = con_y0 + 156
    # Chip 1: Phase Status
    phase_chip_bg = (28, 56, 38) if is_action else (56, 42, 24)
    phase_chip_fg = (143, 225, 150) if is_action else (240, 195, 95)
    phase_chip_txt = (
        f"⚔ ACTION PHASE: {scene.action_summary}"
        if is_action
        else "🔊 VOICEOVER ACTIVE: Pixel world holds still while campaign text is read"
    )
    draw.rounded_rectangle(
        [con_x0 + 28, chip_y, con_x0 + 1140, chip_y + 38],
        radius=16,
        fill=phase_chip_bg,
        outline=phase_chip_fg,
        width=1,
    )
    draw.text(
        (con_x0 + 46, chip_y + 9),
        phase_chip_txt,
        font=get_font("mono_bold", 14),
        fill=phase_chip_fg,
    )

    # Chip 2: Lorekeeper Memory Tool Chip
    mem_chip_active = is_action or prog > 0.65
    draw.rounded_rectangle(
        [con_x0 + 28, chip_y + 50, con_x0 + 1140, chip_y + 88],
        radius=16,
        fill=(38, 33, 24) if mem_chip_active else (26, 23, 18),
        outline=(217, 165, 74) if mem_chip_active else (58, 52, 42),
        width=1,
    )
    draw.text(
        (con_x0 + 46, chip_y + 59),
        f"✦ {scene.memory_chip}",
        font=get_font("mono", 14),
        fill=(217, 165, 74) if mem_chip_active else (120, 110, 95),
    )

    # Right side of Bottom Console: Live Procedural Audio & Voiceover Visualizer + Timeline Bar
    viz_x0, viz_y0, viz_x1, viz_y1 = con_x0 + 1165, con_y0 + 70, con_x1 - 28, con_y1 - 24
    draw.rounded_rectangle(
        [viz_x0, viz_y0, viz_x1, viz_y1],
        radius=8,
        fill=(22, 20, 16),
        outline=(58, 52, 42),
        width=1,
    )

    viz_title = (
        "PROCEDURAL SFX + CHIPTUNE SYNTH [LIVE]"
        if is_action
        else "VOICEOVER SYNTHESIS WAVEFORM [SPEAKING]"
    )
    draw.text(
        (viz_x0 + 18, viz_y0 + 12),
        viz_title,
        font=get_font("mono_bold", 13),
        fill=(143, 191, 122) if is_action else (217, 165, 74),
    )

    # 30-bar frequency/waveform visualizer driven by audio_envelope or deterministic harmonic model
    env_val = 0.5
    if audio_envelope is not None and frame_idx < len(audio_envelope):
        env_val = float(audio_envelope[frame_idx])
    else:
        env_val = 0.65 if not is_action else 0.85

    num_bars = 30
    bar_sp = (viz_x1 - viz_x0 - 36) // num_bars
    mid_y = viz_y0 + 92
    for b_i in range(num_bars):
        wave = abs(math.sin(frame_idx * 0.28 + b_i * 0.45) * math.cos(frame_idx * 0.11 - b_i * 0.2))
        bh = int(max(4, min(46, (8 + wave * 42.0) * (0.35 + 0.85 * env_val))))
        bx = viz_x0 + 18 + b_i * bar_sp
        b_col = (105, 225, 155) if is_action else (230, 178, 78)
        draw.rounded_rectangle([bx, mid_y - bh, bx + bar_sp - 4, mid_y + bh], radius=2, fill=b_col)

    # Overall 45-second progress bar with Scene markers & Contact Sheet pins (8s, 22s, 38s)
    tl_x0, tl_x1, tl_y = viz_x0 + 18, viz_x1 - 18, viz_y1 - 26
    tl_w = tl_x1 - tl_x0
    draw.rounded_rectangle([tl_x0, tl_y, tl_x1, tl_y + 8], radius=4, fill=(44, 38, 30))
    fill_w = int(tl_w * (t / TOTAL_DURATION))
    draw.rounded_rectangle([tl_x0, tl_y, tl_x0 + fill_w, tl_y + 8], radius=4, fill=(217, 165, 74))

    for sc in SCENES:
        sx = tl_x0 + int(tl_w * (sc.start / TOTAL_DURATION))
        ax = tl_x0 + int(tl_w * (sc.still_end / TOTAL_DURATION))
        draw.line([(sx, tl_y - 4), (sx, tl_y + 12)], fill=(140, 128, 110), width=2)
        draw.line([(ax, tl_y - 2), (ax, tl_y + 10)], fill=(95, 210, 140), width=1)

    return frame
