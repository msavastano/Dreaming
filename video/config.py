"""
Editable configuration and scene timing constants for the Lorekeeper
45-second cinematic motion-graphics pixel art action video.

All timings are in seconds (float). Changing any scene timing constant here
automatically updates the renderer, voiceover placement, procedural audio engine,
and contact sheet generator.
"""

from dataclasses import dataclass
from typing import List, Tuple

# ============================================================================
# VIDEO & RENDER SPECIFICATIONS
# ============================================================================
WIDTH: int = 1920
HEIGHT: int = 1080
FPS: int = 60
TOTAL_DURATION: float = 45.0
TOTAL_FRAMES: int = int(TOTAL_DURATION * FPS)  # 2700 frames

# Internal integer-scaled pixel art viewport dimensions (scaled 4x Nearest-Neighbor)
PIXEL_SCALE: int = 4
PIXEL_W: int = 340  # 340 * 4 = 1360 px wide on 1920 canvas
PIXEL_H: int = 164  # 164 * 4 = 656 px high on 1080 canvas
VIEWPORT_X: int = 40
VIEWPORT_Y: int = 84

# Contact sheet check timestamps (in seconds) required before full render
CONTACT_SHEET_TIMESTAMPS: Tuple[float, float, float] = (8.0, 22.0, 38.0)

# Audio specifications
SAMPLE_RATE: int = 44100
AUDIO_CHANNELS: int = 2

# ============================================================================
# EDITABLE SCENE TIMING CONSTANTS (in seconds)
# Each scene has two distinct phases:
#   1. STILL PHASE  [START -> STILL_END]:
#      The pixel-art world holds a frozen tableau while the Voiceover reads
#      the text-based campaign prompt & narration aloud.
#   2. ACTION PHASE [STILL_END -> END]:
#      The pixel-art characters and environment burst into 60fps action with
#      procedural combat/foley sound effects and driving chiptune score.
# ============================================================================

# Scene 1: Arrival at Thornwick Gate & The Crooked Lantern Inn
SCENE_1_START: float = 0.0
SCENE_1_VO_START: float = 0.30
SCENE_1_STILL_END: float = 5.80
SCENE_1_END: float = 11.50

# Scene 2: The Smithy Forge & Elder Maren's Sealed Letter
SCENE_2_START: float = 11.50
SCENE_2_VO_START: float = 11.80
SCENE_2_STILL_END: float = 17.50
SCENE_2_END: float = 25.00

# Scene 3: Moonrise in the Greywood — Battle at the Old Mill
SCENE_3_START: float = 25.00
SCENE_3_VO_START: float = 25.30
SCENE_3_STILL_END: float = 31.00
SCENE_3_END: float = 39.50

# Scene 4: Offline Dreaming — Canon Rebuilt at Dawn Ridge
SCENE_4_START: float = 39.50
SCENE_4_VO_START: float = 39.75
SCENE_4_STILL_END: float = 42.75
SCENE_4_END: float = 45.00


@dataclass(frozen=True)
class SceneSpec:
    """Complete timing and narrative metadata for a single campaign scene."""
    scene_id: int
    slug: str
    title: str
    turn_id: str
    location: str
    start: float
    vo_start: float
    still_end: float
    end: float
    player_move: str
    vo_text: str
    memory_chip: str
    action_summary: str
    hp_start: int
    hp_end: int
    copper_start: int
    copper_end: int


SCENES: List[SceneSpec] = [
    SceneSpec(
        scene_id=1,
        slug="thornwick_arrival",
        title="ACT I // DUSK AT THORNWICK GATE",
        turn_id="s001-t0005",
        location="Thornwick — The Crooked Lantern",
        start=SCENE_1_START,
        vo_start=SCENE_1_VO_START,
        still_end=SCENE_1_STILL_END,
        end=SCENE_1_END,
        player_move="I arrive at Thornwick gate at dusk and ask Hobb at the Crooked Lantern for a room.",
        vo_text="Dusk falls on Thornwick. At the Crooked Lantern, Hobb lends Wren three silver.",
        memory_chip="remembered: owes Hobb 3 silver by full moon [s001-t0005]",
        action_summary="Wren & Pebble stride to the inn; Hobb waves his lantern & tosses 3 silver coins.",
        hp_start=12,
        hp_end=12,
        copper_start=800,
        copper_end=1100,
    ),
    SceneSpec(
        scene_id=2,
        slug="smithy_pact",
        title="ACT II // THE SMITHY & THE SEALED LETTER",
        turn_id="s001-t0009",
        location="Thornwick — Garra's Smithy",
        start=SCENE_2_START,
        vo_start=SCENE_2_VO_START,
        still_end=SCENE_2_STILL_END,
        end=SCENE_2_END,
        player_move="I give Elder Maren the sealed letter, and promise Garra a wolf pelt from the Greywood.",
        vo_text="Elder Maren traces the sealed letter. At the forge, Garra sharpens your blade.",
        memory_chip="remembered: promised Garra a Greywood wolf pelt [s001-t0007]",
        action_summary="Garra hammers the glowing anvil in showers of sparks; Wren catches & slashes the honed blade.",
        hp_start=12,
        hp_end=12,
        copper_start=1100,
        copper_end=1100,
    ),
    SceneSpec(
        scene_id=3,
        slug="greywood_ambush",
        title="ACT III // MOONRISE IN THE GREYWOOD",
        turn_id="s001-t0038",
        location="The Greywood — Old Millstream",
        start=SCENE_3_START,
        vo_start=SCENE_3_VO_START,
        still_end=SCENE_3_STILL_END,
        end=SCENE_3_END,
        player_move="At moonrise I follow tracks past the old mill into the Greywood and draw my short sword.",
        vo_text="Past the old mill, the Greywood wakes. A shadow wolf lunges under the moon.",
        memory_chip="recalled: s001-t0007 (wolf pelt for Garra) -> QUEST COMPLETE",
        action_summary="Dread-Wolf lunges; Wren parries with the blue bead, dashes in, and cleaves the beast under the moon.",
        hp_start=12,
        hp_end=9,
        copper_start=1100,
        copper_end=1100,
    ),
    SceneSpec(
        scene_id=4,
        slug="dreaming_canon",
        title="ACT IV // OFFLINE DREAMING & CANON REBUILT",
        turn_id="dream-pass-01",
        location="Thornwick Ridge — Dawn Overlook",
        start=SCENE_4_START,
        vo_start=SCENE_4_VO_START,
        still_end=SCENE_4_STILL_END,
        end=SCENE_4_END,
        player_move="/dream — Fold campaign turns into wiki pages, verify notes, and rebuild canon.md.",
        vo_text="Dreaming complete. Every promise remembered.",
        memory_chip="canon.md rebuilt: 3 notes confirmed, wiki/wren.md & wiki/garra.md updated",
        action_summary="Wren raises the blade at dawn as golden memory constellations rise into the Lorekeeper emblem.",
        hp_start=9,
        hp_end=12,
        copper_start=1100,
        copper_end=1100,
    ),
]


def get_scene_at_time(t: float) -> Tuple[SceneSpec, bool, float]:
    """
    Return (scene, is_action_phase, phase_progress_0_to_1) for timestamp t.
    """
    t_clamped = max(0.0, min(TOTAL_DURATION - 1e-6, t))
    for scene in SCENES:
        if scene.start <= t_clamped < scene.end or scene is SCENES[-1]:
            if t_clamped < scene.still_end:
                denom = max(1e-6, scene.still_end - scene.start)
                prog = (t_clamped - scene.start) / denom
                return scene, False, max(0.0, min(1.0, prog))
            else:
                denom = max(1e-6, scene.end - scene.still_end)
                prog = (t_clamped - scene.still_end) / denom
                return scene, True, max(0.0, min(1.0, prog))
    return SCENES[-1], True, 1.0
