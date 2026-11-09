"""
Hand-crafted 16-bit pixel art sprites, bitmap font, and low-res pixel canvas
drawing primitives for the Lorekeeper campaign action video.

All drawing functions operate on a NumPy uint8 array of shape (H, W, 3) at
internal pixel resolution (340 x 164), which is then integer-upscaled 4x with
nearest-neighbor filtering to produce razor-sharp pixel art at 1920x1080.
"""

from typing import Dict, List, Optional, Tuple
import math
import numpy as np

Color = Tuple[int, int, int]

# ============================================================================
# PIXEL BITMAP FONT (3x5 and 5x7 crisp pixel glyphs for floating RPG combat text)
# ============================================================================
FONT_3X5: Dict[str, List[str]] = {
    "A": ["010", "101", "111", "101", "101"],
    "B": ["110", "101", "110", "101", "110"],
    "C": ["011", "100", "100", "100", "011"],
    "D": ["110", "101", "101", "101", "110"],
    "E": ["111", "100", "110", "100", "111"],
    "F": ["111", "100", "110", "100", "100"],
    "G": ["011", "100", "101", "101", "011"],
    "H": ["101", "101", "111", "101", "101"],
    "I": ["111", "010", "010", "010", "111"],
    "J": ["001", "001", "001", "101", "010"],
    "K": ["101", "101", "110", "101", "101"],
    "L": ["100", "100", "100", "100", "111"],
    "M": ["101", "111", "111", "101", "101"],
    "N": ["110", "101", "101", "101", "101"],
    "O": ["010", "101", "101", "101", "010"],
    "P": ["110", "101", "110", "100", "100"],
    "Q": ["010", "101", "101", "011", "001"],
    "R": ["110", "101", "110", "101", "101"],
    "S": ["011", "100", "010", "001", "110"],
    "T": ["111", "010", "010", "010", "010"],
    "U": ["101", "101", "101", "101", "111"],
    "V": ["101", "101", "101", "101", "010"],
    "W": ["101", "101", "111", "111", "101"],
    "X": ["101", "101", "010", "101", "101"],
    "Y": ["101", "101", "010", "010", "010"],
    "Z": ["111", "001", "010", "100", "111"],
    "0": ["111", "101", "101", "101", "111"],
    "1": ["010", "110", "010", "010", "111"],
    "2": ["110", "001", "010", "100", "111"],
    "3": ["110", "001", "010", "001", "110"],
    "4": ["101", "101", "111", "001", "001"],
    "5": ["111", "100", "110", "001", "110"],
    "6": ["011", "100", "111", "101", "111"],
    "7": ["111", "001", "010", "010", "010"],
    "8": ["111", "101", "111", "101", "111"],
    "9": ["111", "101", "111", "001", "110"],
    "+": ["000", "010", "111", "010", "000"],
    "-": ["000", "000", "111", "000", "000"],
    "!": ["010", "010", "010", "000", "010"],
    ":": ["000", "010", "000", "010", "000"],
    ".": ["000", "000", "000", "000", "010"],
    "/": ["001", "001", "010", "100", "100"],
    " ": ["000", "000", "000", "000", "000"],
}


# ============================================================================
# LOW-LEVEL PIXEL CANVAS PRIMITIVES
# ============================================================================
def put_px(canvas: np.ndarray, x: int, y: int, color: Color, alpha: float = 1.0) -> None:
    """Plot a single pixel with optional alpha blending."""
    h, w, _ = canvas.shape
    ix, iy = int(round(x)), int(round(y))
    if 0 <= ix < w and 0 <= iy < h:
        if alpha >= 0.999:
            canvas[iy, ix] = color
        elif alpha > 0.001:
            bg = canvas[iy, ix].astype(np.float32)
            fg = np.array(color, dtype=np.float32)
            canvas[iy, ix] = np.clip(bg * (1.0 - alpha) + fg * alpha, 0, 255).astype(np.uint8)


def fill_rect(
    canvas: np.ndarray,
    x: int,
    y: int,
    rw: int,
    rh: int,
    color: Color,
    alpha: float = 1.0,
) -> None:
    """Fill an axis-aligned rectangle on the pixel canvas."""
    h, w, _ = canvas.shape
    x0 = max(0, int(round(x)))
    y0 = max(0, int(round(y)))
    x1 = min(w, int(round(x + rw)))
    y1 = min(h, int(round(y + rh)))
    if x1 <= x0 or y1 <= y0:
        return
    if alpha >= 0.999:
        canvas[y0:y1, x0:x1] = color
    elif alpha > 0.001:
        region = canvas[y0:y1, x0:x1].astype(np.float32)
        fg = np.array(color, dtype=np.float32)
        canvas[y0:y1, x0:x1] = np.clip(region * (1.0 - alpha) + fg * alpha, 0, 255).astype(np.uint8)


def draw_line(
    canvas: np.ndarray,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    color: Color,
    thickness: int = 1,
    alpha: float = 1.0,
) -> None:
    """Bresenham-style pixel line with optional thickness."""
    ix0, iy0 = int(round(x0)), int(round(y0))
    ix1, iy1 = int(round(x1)), int(round(y1))
    steps = max(abs(ix1 - ix0), abs(iy1 - iy0), 1)
    for i in range(steps + 1):
        t = i / steps
        px = int(round(ix0 + (ix1 - ix0) * t))
        py = int(round(iy0 + (iy1 - iy0) * t))
        if thickness <= 1:
            put_px(canvas, px, py, color, alpha)
        else:
            r = thickness // 2
            fill_rect(canvas, px - r, py - r, thickness, thickness, color, alpha)


def draw_circle(
    canvas: np.ndarray,
    cx: float,
    cy: float,
    radius: float,
    color: Color,
    fill: bool = True,
    alpha: float = 1.0,
) -> None:
    """Draw a filled or outlined pixel circle."""
    h, w, _ = canvas.shape
    r = int(math.ceil(radius))
    icx, icy = int(round(cx)), int(round(cy))
    y0, y1 = max(0, icy - r), min(h, icy + r + 1)
    x0, x1 = max(0, icx - r), min(w, icx + r + 1)
    if y1 <= y0 or x1 <= x0:
        return
    yy, xx = np.ogrid[y0:y1, x0:x1]
    dist2 = (xx - cx) ** 2 + (yy - cy) ** 2
    if fill:
        mask = dist2 <= radius ** 2
    else:
        mask = (dist2 <= radius ** 2) & (dist2 >= max(0.0, radius - 1.2) ** 2)
    if alpha >= 0.999:
        canvas[y0:y1, x0:x1][mask] = color
    elif alpha > 0.001:
        sub = canvas[y0:y1, x0:x1]
        blended = np.clip(
            sub[mask].astype(np.float32) * (1.0 - alpha)
            + np.array(color, dtype=np.float32) * alpha,
            0,
            255,
        ).astype(np.uint8)
        sub[mask] = blended


def draw_glow(
    canvas: np.ndarray,
    cx: float,
    cy: float,
    radius: float,
    color: Color,
    intensity: float = 0.45,
) -> None:
    """Additive/soft radial pixel light glow."""
    if intensity <= 0.01 or radius <= 1.0:
        return
    h, w, _ = canvas.shape
    r = int(math.ceil(radius))
    icx, icy = int(round(cx)), int(round(cy))
    y0, y1 = max(0, icy - r), min(h, icy + r + 1)
    x0, x1 = max(0, icx - r), min(w, icx + r + 1)
    if y1 <= y0 or x1 <= x0:
        return
    yy, xx = np.ogrid[y0:y1, x0:x1]
    dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    falloff = np.clip(1.0 - dist / radius, 0.0, 1.0) ** 1.8 * intensity
    # Quantize falloff into 4 pixel-art dither/banding steps for authentic retro feel
    falloff = np.floor(falloff * 6.0) / 6.0
    sub = canvas[y0:y1, x0:x1].astype(np.float32)
    col = np.array(color, dtype=np.float32)
    added = sub + falloff[..., None] * col
    canvas[y0:y1, x0:x1] = np.clip(added, 0, 255).astype(np.uint8)


def draw_pixel_text(
    canvas: np.ndarray,
    text: str,
    x: int,
    y: int,
    color: Color = (255, 245, 210),
    shadow: Optional[Color] = (15, 12, 10),
    scale: int = 1,
) -> None:
    """Render crisp 3x5 pixel text directly onto the low-res pixel canvas."""
    cursor_x = int(round(x))
    iy = int(round(y))
    for ch in text.upper():
        glyph = FONT_3X5.get(ch, FONT_3X5[" "])
        gw = len(glyph[0]) if glyph else 3
        for row_idx, row_str in enumerate(glyph):
            for col_idx, bit in enumerate(row_str):
                if bit == "1":
                    px = cursor_x + col_idx * scale
                    py = iy + row_idx * scale
                    if shadow is not None:
                        fill_rect(canvas, px + scale, py + scale, scale, scale, shadow)
                    fill_rect(canvas, px, py, scale, scale, color)
        cursor_x += (gw + 1) * scale


def draw_sprite_matrix(
    canvas: np.ndarray,
    matrix: List[str],
    palette: Dict[str, Color],
    x: float,
    y: float,
    flip_x: bool = False,
    tint: Optional[Color] = None,
    alpha: float = 1.0,
) -> None:
    """Render a character-mapped sprite matrix onto the pixel canvas."""
    ix, iy = int(round(x)), int(round(y))
    for r_idx, row in enumerate(matrix):
        row_iter = reversed(row) if flip_x else row
        for c_idx, key in enumerate(row_iter):
            if key == "." or key == " ":
                continue
            col = tint if tint is not None else palette.get(key)
            if col is not None:
                put_px(canvas, ix + c_idx, iy + r_idx, col, alpha)


# ============================================================================
# CHARACTER SPRITES
# ============================================================================

WREN_PALETTE: Dict[str, Color] = {
    "o": (18, 16, 24),       # Dark outline
    "c": (32, 78, 68),       # Deep emerald traveling cloak
    "C": (52, 118, 102),     # Cloak highlight
    "d": (20, 50, 44),       # Cloak deep shadow
    "f": (240, 202, 170),    # Face / skin
    "e": (30, 24, 28),       # Eye
    "h": (78, 48, 34),       # Chestnut hair
    "t": (118, 76, 46),      # Leather tunic
    "T": (156, 104, 64),     # Tunic highlight
    "g": (230, 184, 74),     # Belt gold buckle
    "b": (76, 230, 255),     # Blue glass bead charm (mother's charm)
    "B": (190, 250, 255),    # Bead core glow
    "p": (58, 52, 68),       # Trousers
    "l": (52, 34, 24),       # Boots
    "s": (210, 224, 240),    # Steel blade
    "S": (255, 255, 255),    # Blade edge gleam
    "w": (165, 178, 198),    # Wolf pelt silver fur
    "W": (220, 230, 245),    # Wolf pelt highlight
}

WREN_IDLE_MATRIX: List[str] = [
    "....oooooo......",
    "...oCCCCCCo.....",
    "..oCCcchhCCo....",
    "..oCchfffhcCo...",
    "..oCcfefefcCo...",
    "...oCfffffcCo...",
    "...oCCbBbgCCo...",
    "..oCCCtTTtCCCo..",
    "..oCCctTTtcCCo..",
    ".oCCCggggggCCCo.",
    ".oCCcchttthcCCo.",
    ".oCCccppppccCCo.",
    "..oCccppppccCo..",
    "..oCccppppccCo..",
    "...o..llll..o...",
    "......llll......",
]


def draw_wren(
    canvas: np.ndarray,
    x: float,
    y: float,
    pose: str = "idle",
    frame: int = 0,
    flip_x: bool = False,
    has_wolf_pelt: bool = False,
    afterimage_tint: Optional[Color] = None,
    alpha: float = 1.0,
) -> None:
    """
    Draw Wren (the hero) at (x, y) where (x, y) is top-left of the 16x16 body box.
    Supports poses: 'idle', 'walk', 'salute', 'catch_slash', 'combat_ready',
    'parry', 'dash_slash', 'leap_cleave', 'victory'.
    """
    bob = 0
    if pose == "walk":
        bob = -1 if (frame % 4) in (1, 3) else 0
    elif pose in ("combat_ready", "parry"):
        bob = 1

    bx, by = int(round(x)), int(round(y)) + bob

    # Cloak billowing tail behind Wren during movement/action
    dir_sign = -1 if flip_x else 1
    if pose in ("walk", "catch_slash", "dash_slash", "leap_cleave", "victory"):
        flap = int(math.sin(frame * 0.45) * 2)
        for i in range(1, 7):
            cx = bx + (8 - dir_sign * (4 + i))
            cy = by + 6 + (i // 2) + flap
            fill_rect(canvas, cx, cy, 3, 5, WREN_PALETTE["d"] if i > 3 else WREN_PALETTE["c"], alpha)

    # Base body sprite
    draw_sprite_matrix(canvas, WREN_IDLE_MATRIX, WREN_PALETTE, bx, by, flip_x=flip_x, tint=afterimage_tint, alpha=alpha)

    if afterimage_tint is not None:
        return

    # Animated legs override for walk / dash / leap
    if pose == "walk":
        step = frame % 4
        fill_rect(canvas, bx + 5, by + 14, 6, 2, (0, 0, 0), alpha=0.0)  # no-op placeholder
        leg_offsets = [(-2, 2), (0, 0), (2, -2), (0, 0)][step]
        fill_rect(canvas, bx + 5 + leg_offsets[0], by + 14, 2, 3, WREN_PALETTE["l"])
        fill_rect(canvas, bx + 9 + leg_offsets[1], by + 14, 2, 3, WREN_PALETTE["l"])
    elif pose == "leap_cleave":
        fill_rect(canvas, bx + 4, by + 13, 3, 3, WREN_PALETTE["l"])
        fill_rect(canvas, bx + 10, by + 12, 3, 3, WREN_PALETTE["l"])

    # Optional silver Wolf Pelt draped over shoulders (Scene 4)
    if has_wolf_pelt:
        fill_rect(canvas, bx + 2, by + 5, 12, 3, WREN_PALETTE["w"])
        fill_rect(canvas, bx + 3, by + 5, 9, 1, WREN_PALETTE["W"])

    # Blue glass bead glow at collar
    bead_x = bx + (9 if flip_x else 6)
    bead_y = by + 6
    draw_glow(canvas, bead_x, bead_y, 4.0, (80, 230, 255), 0.35)

    # Short Sword rendering by pose
    hand_x = bx + (3 if flip_x else 12)
    hand_y = by + 9

    if pose == "idle":
        # Sheathed at hip with golden pommel glinting
        put_px(canvas, hand_x - dir_sign * 2, hand_y + 1, WREN_PALETTE["g"])
        draw_line(canvas, hand_x - dir_sign * 3, hand_y + 2, hand_x - dir_sign * 7, hand_y + 5, WREN_PALETTE["s"], 1)
    elif pose == "walk":
        put_px(canvas, hand_x - dir_sign * 2, hand_y + 1, WREN_PALETTE["g"])
        draw_line(canvas, hand_x - dir_sign * 3, hand_y + 2, hand_x - dir_sign * 7, hand_y + 5, WREN_PALETTE["s"], 1)
    elif pose == "salute":
        # Raising hand to catch Hobb's silver coins
        fill_rect(canvas, hand_x + dir_sign * 2, hand_y - 4, 2, 3, WREN_PALETTE["f"])
    elif pose == "combat_ready":
        # Sword drawn forward, angled menacingly
        put_px(canvas, hand_x, hand_y, WREN_PALETTE["g"])
        draw_line(canvas, hand_x + dir_sign * 1, hand_y - 1, hand_x + dir_sign * 11, hand_y - 4, WREN_PALETTE["s"], 2)
        draw_line(canvas, hand_x + dir_sign * 2, hand_y - 2, hand_x + dir_sign * 11, hand_y - 4, WREN_PALETTE["S"], 1)
    elif pose == "parry":
        # Sword held vertically with blue glass bead magic ward
        draw_line(canvas, hand_x + dir_sign * 3, hand_y + 3, hand_x + dir_sign * 4, hand_y - 10, WREN_PALETTE["S"], 2)
        put_px(canvas, hand_x + dir_sign * 3, hand_y + 1, WREN_PALETTE["g"])
        draw_circle(canvas, bx + 8 + dir_sign * 5, by + 7, 11, (90, 235, 255), fill=False, alpha=0.85)
        draw_glow(canvas, bx + 8 + dir_sign * 5, by + 7, 14, (70, 220, 255), 0.55)
    elif pose in ("catch_slash", "dash_slash", "leap_cleave"):
        # Extended glowing short sword + sweeping crescent slash arc
        put_px(canvas, hand_x + dir_sign, hand_y - 2, WREN_PALETTE["g"])
        tip_x = hand_x + dir_sign * 15
        tip_y = hand_y - 9 if pose != "dash_slash" else hand_y - 2
        draw_line(canvas, hand_x + dir_sign, hand_y - 2, tip_x, tip_y, WREN_PALETTE["s"], 2)
        draw_line(canvas, hand_x + dir_sign * 2, hand_y - 3, tip_x, tip_y, WREN_PALETTE["S"], 1)
    elif pose == "victory":
        # Sword raised straight toward the dawn sky
        put_px(canvas, hand_x + dir_sign, by + 4, WREN_PALETTE["g"])
        draw_line(canvas, hand_x + dir_sign, by + 3, hand_x + dir_sign, by - 11, WREN_PALETTE["S"], 2)
        draw_glow(canvas, hand_x + dir_sign, by - 6, 8.0, (255, 225, 120), 0.5)


def draw_sword_slash_arc(
    canvas: np.ndarray,
    cx: float,
    cy: float,
    radius: float,
    angle_start_deg: float,
    angle_end_deg: float,
    color_outer: Color = (255, 210, 75),
    color_inner: Color = (255, 255, 230),
    thickness: int = 4,
) -> None:
    """Draw a dramatic multi-layered pixel-art crescent sword slash trail."""
    steps = 36
    for i in range(steps + 1):
        t = i / steps
        ang = math.radians(angle_start_deg + (angle_end_deg - angle_start_deg) * t)
        # Taper thickness at ends of the crescent
        envelope = math.sin(t * math.pi)
        cur_thick = max(1, int(round(thickness * envelope)))
        px = cx + math.cos(ang) * radius
        py = cy + math.sin(ang) * (radius * 0.72)
        fill_rect(canvas, int(px) - cur_thick // 2, int(py) - cur_thick // 2, cur_thick, cur_thick, color_outer)
        if envelope > 0.35:
            px_in = cx + math.cos(ang) * (radius - 1.5)
            py_in = cy + math.sin(ang) * ((radius - 1.5) * 0.72)
            fill_rect(canvas, int(px_in), int(py_in), max(1, cur_thick - 1), max(1, cur_thick - 1), color_inner)


# ============================================================================
# PEBBLE THE GREY MULE
# ============================================================================
def draw_pebble_mule(
    canvas: np.ndarray,
    x: float,
    y: float,
    walking: bool = False,
    frame: int = 0,
) -> None:
    """Draw Pebble the grey mule with leather saddlebags."""
    ix, iy = int(round(x)), int(round(y))
    bob = -1 if (walking and (frame % 4) in (1, 3)) else 0
    iy += bob

    grey_dark = (88, 94, 106)
    grey_mid = (128, 136, 150)
    grey_light = (166, 175, 190)
    pack_brown = (128, 78, 42)
    pack_gold = (220, 175, 72)

    # Legs (animated when walking)
    step = (frame % 4) if walking else 0
    l1 = 1 if step == 1 else (-1 if step == 3 else 0)
    l2 = -1 if step == 1 else (1 if step == 3 else 0)
    fill_rect(canvas, ix + 3 + l1, iy + 11, 2, 6, grey_dark)
    fill_rect(canvas, ix + 7 + l2, iy + 11, 2, 6, grey_mid)
    fill_rect(canvas, ix + 14 + l2, iy + 11, 2, 6, grey_dark)
    fill_rect(canvas, ix + 18 + l1, iy + 11, 2, 6, grey_mid)

    # Body & rump
    fill_rect(canvas, ix + 2, iy + 5, 18, 7, grey_mid)
    fill_rect(canvas, ix + 3, iy + 5, 15, 2, grey_light)
    # Tail
    draw_line(canvas, ix + 1, iy + 6, ix - 1, iy + 11, grey_dark, 1)

    # Saddlebag pack
    fill_rect(canvas, ix + 7, iy + 4, 8, 6, pack_brown)
    fill_rect(canvas, ix + 8, iy + 4, 6, 1, pack_gold)
    put_px(canvas, ix + 11, iy + 7, pack_gold)

    # Neck & head (facing right)
    fill_rect(canvas, ix + 17, iy + 1, 4, 6, grey_mid)
    fill_rect(canvas, ix + 19, iy + 1, 5, 4, grey_light)
    put_px(canvas, ix + 21, iy + 2, (20, 18, 22))  # Eye
    # Long mule ears!
    fill_rect(canvas, ix + 17, iy - 3, 1, 4, grey_dark)
    fill_rect(canvas, ix + 19, iy - 3, 1, 4, grey_mid)


# ============================================================================
# HOBB THE HALFLING INNKEEPER
# ============================================================================
def draw_hobb(
    canvas: np.ndarray,
    x: float,
    y: float,
    active: bool = False,
    frame: int = 0,
) -> None:
    """Draw Hobb the talkative halfling innkeeper holding a warm brass lantern."""
    ix, iy = int(round(x)), int(round(y))
    hop = -1 if (active and (frame // 4) % 2 == 1) else 0
    iy += hop

    # Curly brown hair & warm face
    fill_rect(canvas, ix + 4, iy, 6, 2, (98, 62, 36))
    fill_rect(canvas, ix + 4, iy + 2, 6, 4, (238, 194, 160))
    put_px(canvas, ix + 5, iy + 3, (25, 20, 20))
    put_px(canvas, ix + 8, iy + 3, (25, 20, 20))

    # Burgundy waistcoat & white tavern apron
    fill_rect(canvas, ix + 3, iy + 6, 8, 6, (152, 48, 48))
    fill_rect(canvas, ix + 4, iy + 8, 6, 4, (236, 228, 212))
    # Halfling bare feet / short legs
    fill_rect(canvas, ix + 4, iy + 12, 2, 2, (76, 52, 34))
    fill_rect(canvas, ix + 8, iy + 12, 2, 2, (76, 52, 34))

    # Raised arm holding glowing lantern (left of Hobb)
    lantern_swing = int(math.sin(frame * 0.25) * 2) if active else 0
    lx = ix - 3 + lantern_swing
    ly = iy + (4 if active else 6)
    draw_line(canvas, ix + 3, iy + 7, lx + 1, ly - 2, (236, 228, 212), 1)
    fill_rect(canvas, lx, ly, 3, 4, (255, 200, 70))
    put_px(canvas, lx + 1, ly + 1, (255, 250, 210))
    draw_glow(canvas, lx + 1, ly + 2, 14.0 if active else 10.0, (255, 175, 60), 0.45)


# ============================================================================
# GARRA THE BLACKSMITH (WITH BURN-SCARRED LEFT HAND & ANVIL HAMMER)
# ============================================================================
def draw_garra(
    canvas: np.ndarray,
    x: float,
    y: float,
    hammer_phase: float = 0.0,
    is_action: bool = False,
) -> None:
    """
    Draw Garra the broad blacksmith behind the anvil.
    hammer_phase in [0, 1]: 0.0 = hammer raised high, 0.5 = slamming down on anvil.
    """
    ix, iy = int(round(x)), int(round(y))

    # Hair & head
    fill_rect(canvas, ix + 5, iy, 7, 3, (46, 32, 28))
    fill_rect(canvas, ix + 5, iy + 2, 6, 5, (214, 158, 122))
    put_px(canvas, ix + 6, iy + 4, (24, 18, 18))

    # Broad shoulders, tunic & heavy leather smith apron
    fill_rect(canvas, ix + 2, iy + 7, 12, 10, (74, 48, 32))
    fill_rect(canvas, ix + 4, iy + 8, 8, 9, (112, 72, 46))
    # Boots
    fill_rect(canvas, ix + 4, iy + 17, 3, 3, (40, 28, 22))
    fill_rect(canvas, ix + 9, iy + 17, 3, 3, (40, 28, 22))

    # Left arm stabilizing tongs on the anvil (with burn scar highlight)
    fill_rect(canvas, ix - 2, iy + 9, 4, 2, (214, 158, 122))
    put_px(canvas, ix - 1, iy + 9, (248, 210, 195))  # Burn scar on left hand

    # Right arm & heavy blacksmith hammer
    if not is_action or hammer_phase < 0.35 or hammer_phase > 0.75:
        # Hammer poised high above the anvil
        fill_rect(canvas, ix + 11, iy + 4, 3, 5, (214, 158, 122))
        draw_line(canvas, ix + 12, iy + 3, ix + 9, iy - 4, (140, 96, 54), 1)
        fill_rect(canvas, ix + 6, iy - 6, 6, 3, (165, 178, 195))
    else:
        # Hammer slamming down onto the glowing steel on the anvil!
        fill_rect(canvas, ix + 10, iy + 8, 3, 4, (214, 158, 122))
        draw_line(canvas, ix + 10, iy + 10, ix + 2, iy + 11, (140, 96, 54), 1)
        fill_rect(canvas, ix - 2, iy + 9, 5, 3, (195, 208, 225))


# ============================================================================
# ELDER MAREN (BLIND VILLAGE ELDER WITH SEALED LETTER)
# ============================================================================
def draw_maren(
    canvas: np.ndarray,
    x: float,
    y: float,
    seal_broken: bool = False,
    frame: int = 0,
) -> None:
    """Draw blind Elder Maren tracing the sealed wax letter with her fingers."""
    ix, iy = int(round(x)), int(round(y))

    # Silver hair & shawl hood
    fill_rect(canvas, ix + 4, iy, 6, 3, (205, 212, 226))
    fill_rect(canvas, ix + 4, iy + 2, 6, 4, (232, 198, 172))
    # Serene closed eyes (blind elder)
    draw_line(canvas, ix + 5, iy + 4, ix + 6, iy + 4, (90, 75, 75), 1)
    draw_line(canvas, ix + 8, iy + 4, ix + 9, iy + 4, (90, 75, 75), 1)

    # Deep indigo robes & woven shawl
    fill_rect(canvas, ix + 2, iy + 6, 10, 12, (62, 50, 92))
    fill_rect(canvas, ix + 3, iy + 6, 8, 5, (92, 76, 134))
    fill_rect(canvas, ix + 4, iy + 7, 6, 1, (218, 165, 74))  # Gold shawl trim

    # Hands holding the parchment letter with crimson wax seal
    lx = ix + 11
    ly = iy + 8 + (int(math.sin(frame * 0.15)) if seal_broken else 0)
    fill_rect(canvas, lx, ly, 5, 4, (238, 226, 196))
    put_px(canvas, lx + 2, ly + 2, (220, 42, 42))  # Red wax seal
    if seal_broken:
        draw_glow(canvas, lx + 2, ly + 1, 9.0, (255, 205, 95), 0.45)


# ============================================================================
# THE GREYWOOD DREAD-WOLF (LARGE BOSS SPRITE)
# ============================================================================
def draw_dread_wolf(
    canvas: np.ndarray,
    x: float,
    y: float,
    pose: str = "still",
    frame: int = 0,
    alpha: float = 1.0,
) -> None:
    """
    Draw the giant Greywood Dread-Wolf (facing left toward Wren).
    Poses: 'still', 'lunge', 'recoil', 'cleaved'.
    """
    ix, iy = int(round(x)), int(round(y))
    fur_dark = (26, 30, 42)
    fur_mid = (46, 54, 72)
    fur_silver = (130, 146, 175)
    eye_red = (255, 38, 68)
    fang_white = (245, 248, 255)

    if pose == "cleaved":
        # Dissolving in crimson/silver shadow-embers when defeated
        spread = min(14, frame // 2)
        fill_rect(canvas, ix + 6, iy - spread, 24, 7, fur_dark, alpha=max(0.0, alpha * 0.6))
        fill_rect(canvas, ix + 8, iy + 7 + spread, 24, 7, fur_mid, alpha=max(0.0, alpha * 0.6))
        return

    leap_y = -4 if pose == "lunge" else (2 if pose == "recoil" else 0)
    iy += leap_y

    # Shadow aura around the Dread-Wolf in action phase
    if pose != "still":
        draw_glow(canvas, ix + 16, iy + 9, 18.0, (180, 30, 60), 0.25)

    # Hindquarters & jagged back fur
    fill_rect(canvas, ix + 10, iy + 5, 22, 10, fur_dark, alpha)
    fill_rect(canvas, ix + 8, iy + 4, 18, 8, fur_mid, alpha)
    # Jagged silver-tipped spine hackles
    for spike in range(5):
        sx = ix + 9 + spike * 4
        fill_rect(canvas, sx, iy + 1, 3, 3, fur_silver, alpha)

    # Bushy shadow tail
    fill_rect(canvas, ix + 31, iy + 3, 7, 5, fur_dark, alpha)
    fill_rect(canvas, ix + 33, iy + 2, 5, 2, fur_silver, alpha)

    # Wolf head, snarling snout & fangs (facing left)
    fill_rect(canvas, ix + 1, iy + 3, 10, 8, fur_mid, alpha)
    fill_rect(canvas, ix - 3, iy + 5, 6, 4, fur_dark, alpha)
    # Pointed ears
    fill_rect(canvas, ix + 6, iy, 2, 3, fur_silver, alpha)
    fill_rect(canvas, ix + 9, iy + 1, 2, 2, fur_dark, alpha)
    # Glowing crimson eye + trail
    put_px(canvas, ix + 3, iy + 5, eye_red, alpha)
    put_px(canvas, ix + 4, iy + 5, (255, 160, 175), alpha)
    draw_glow(canvas, ix + 3, iy + 5, 6.0, eye_red, 0.5 * alpha)
    # Sharp white pixel fangs
    put_px(canvas, ix - 2, iy + 9, fang_white, alpha)
    put_px(canvas, ix, iy + 9, fang_white, alpha)
    put_px(canvas, ix + 2, iy + 9, fang_white, alpha)

    # Legs (extended in lunge, braced in still/recoil)
    if pose == "lunge":
        draw_line(canvas, ix + 4, iy + 12, ix - 5, iy + 16, fur_dark, 2, alpha)
        draw_line(canvas, ix + 8, iy + 13, ix - 2, iy + 18, fur_mid, 2, alpha)
        draw_line(canvas, ix + 24, iy + 13, ix + 32, iy + 17, fur_dark, 2, alpha)
        # Crimson claw swipe streaks!
        draw_line(canvas, ix - 6, iy + 14, ix - 13, iy + 18, eye_red, 1, alpha)
        draw_line(canvas, ix - 5, iy + 16, ix - 12, iy + 20, (255, 130, 150), 1, alpha)
    else:
        fill_rect(canvas, ix + 6, iy + 13, 3, 7, fur_dark, alpha)
        fill_rect(canvas, ix + 11, iy + 13, 3, 7, fur_mid, alpha)
        fill_rect(canvas, ix + 22, iy + 13, 3, 7, fur_dark, alpha)
        fill_rect(canvas, ix + 27, iy + 13, 3, 7, fur_mid, alpha)
