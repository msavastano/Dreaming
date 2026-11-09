"""
Procedural audio engine and voiceover synthesizer for the Lorekeeper
45-second pixel art action video.

All sounds are generated in code using NumPy and ffmpeg's built-in libflite
synthesizer:
  1. Voiceover narration reading each scene's campaign text during the STILL phase.
  2. Typewriter clicks and STILL -> ACTION transition stingers.
  3. Scene-specific action SFX (footsteps, silver coin chimes, anvil hammer clangs,
     magic ward parry, wolf growls, sword slashes, critical-hit cleave, dreaming harp).
  4. Adaptive 16-bit chiptune & synth score (gentle lute arpeggio ducked under VO
     in STILL phases; driving percussion, bassline, and heroic lead in ACTION phases).
"""

import math
import os
import subprocess
import tempfile
import wave
from typing import Dict, List, Tuple
import numpy as np

from video.config import (
    FPS,
    SAMPLE_RATE,
    SCENES,
    TOTAL_DURATION,
    TOTAL_FRAMES,
)


def _synth_flite_voice(text: str, voice: str = "rms") -> np.ndarray:
    """Synthesize speech mono float32 array at SAMPLE_RATE using ffmpeg's libflite."""
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as tf:
        tf.write(text)
        txt_path = tf.name
    wav_path = txt_path + ".wav"
    try:
        cmd = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"flite=textfile={txt_path}:voice={voice}",
            "-af",
            "atempo=1.06,lowpass=f=7500,highpass=f=85",
            "-ar",
            str(SAMPLE_RATE),
            "-ac",
            "1",
            wav_path,
        ]
        subprocess.run(cmd, check=True)
        with wave.open(wav_path, "rb") as wf:
            raw = wf.readframes(wf.getnframes())
            samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    finally:
        for p in (txt_path, wav_path):
            if os.path.exists(p):
                os.remove(p)

    # Normalize & add warm narrator body + subtle stereo-ready presence
    peak = np.max(np.abs(samples))
    if peak > 1e-4:
        samples = samples / peak * 0.88
    return samples


def _add_mono_to_stereo(
    stereo: np.ndarray,
    mono: np.ndarray,
    start_time: float,
    pan: float = 0.0,
    gain: float = 1.0,
) -> None:
    """Mix a mono signal into a stereo buffer (N, 2) at start_time with pan in [-1, 1]."""
    start_idx = int(round(start_time * SAMPLE_RATE))
    if start_idx >= len(stereo) or len(mono) == 0:
        return
    if start_idx < 0:
        mono = mono[-start_idx:]
        start_idx = 0
    end_idx = min(len(stereo), start_idx + len(mono))
    seg = mono[: end_idx - start_idx]
    angle = (pan + 1.0) * (math.pi / 4.0)
    gain_l = math.cos(angle) * gain
    gain_r = math.sin(angle) * gain
    stereo[start_idx:end_idx, 0] += seg * gain_l
    stereo[start_idx:end_idx, 1] += seg * gain_r


def synth_coin_chime(duration: float = 0.45, pitch_mult: float = 1.0) -> np.ndarray:
    """Bright metallic silver coin toss & catch ring."""
    n = int(SAMPLE_RATE * duration)
    t = np.arange(n, dtype=np.float32) / SAMPLE_RATE
    freqs = [2350.0 * pitch_mult, 3520.0 * pitch_mult, 5180.0 * pitch_mult]
    env = np.exp(-t * 11.0)
    sig = sum(np.sin(2.0 * math.pi * f * t) * (0.5 / (i + 1)) for i, f in enumerate(freqs))
    return (sig * env).astype(np.float32)


def synth_anvil_strike(duration: float = 0.55) -> np.ndarray:
    """Heavy blacksmith hammer striking glowing steel on an iron anvil."""
    n = int(SAMPLE_RATE * duration)
    t = np.arange(n, dtype=np.float32) / SAMPLE_RATE
    # Inharmonic metallic anvil modes + low hammer impact thud + spark sizzle
    modes = [880.0, 1690.0, 2540.0, 3910.0]
    ring = sum(
        np.sin(2.0 * math.pi * f * t) * np.exp(-t * (8.0 + i * 4.5)) * (0.45 / (i + 1))
        for i, f in enumerate(modes)
    )
    thud = np.sin(2.0 * math.pi * (135.0 * np.exp(-t * 25.0) + 55.0) * t) * np.exp(-t * 28.0) * 0.65
    rng = np.random.default_rng(42)
    sizzle = rng.normal(0.0, 1.0, n).astype(np.float32) * np.exp(-t * 18.0) * 0.18
    return np.clip(ring + thud + sizzle, -1.0, 1.0).astype(np.float32)


def synth_sword_slash(duration: float = 0.38, heavy: bool = False) -> np.ndarray:
    """Sweeping metallic blade whoosh + edge ring."""
    n = int(SAMPLE_RATE * duration)
    t = np.arange(n, dtype=np.float32) / SAMPLE_RATE
    rng = np.random.default_rng(101 if heavy else 77)
    noise = rng.normal(0.0, 1.0, n).astype(np.float32)
    # Swept frequency carrier for aerodynamic whoosh
    sweep_f = np.linspace(450.0, 2200.0 if heavy else 1600.0, n)
    carrier = np.sin(2.0 * math.pi * np.cumsum(sweep_f) / SAMPLE_RATE)
    env = np.sin(np.pi * (t / duration)) ** 1.4
    whoosh = noise * carrier * env * (0.55 if heavy else 0.42)
    # Metallic steel ring
    blade_ring = (
        np.sin(2.0 * math.pi * (1420.0 if heavy else 1820.0) * t)
        * np.exp(-t * 10.0)
        * (0.45 if heavy else 0.28)
    )
    if heavy:
        sub_boom = np.sin(2.0 * math.pi * (95.0 * np.exp(-t * 12.0) + 42.0) * t) * np.exp(-t * 9.0) * 0.65
        return np.clip(whoosh + blade_ring + sub_boom, -1.0, 1.0).astype(np.float32)
    return np.clip(whoosh + blade_ring, -1.0, 1.0).astype(np.float32)


def synth_wolf_growl(duration: float = 0.65) -> np.ndarray:
    """Menacing low sawtooth/formant growl for the Greywood Dread-Wolf."""
    n = int(SAMPLE_RATE * duration)
    t = np.arange(n, dtype=np.float32) / SAMPLE_RATE
    f0 = 82.0 + 28.0 * np.sin(2.0 * math.pi * 2.2 * t) + 8.0 * np.sin(2.0 * math.pi * 24.0 * t)
    phase = 2.0 * math.pi * np.cumsum(f0) / SAMPLE_RATE
    saw = 2.0 * ((phase / (2.0 * math.pi)) % 1.0) - 1.0
    formant = np.sin(phase * 2.0) * 0.5 + np.sin(phase * 3.0) * 0.3
    env = np.sin(np.pi * (t / duration)) ** 0.8
    return ((saw * 0.4 + formant) * env * 0.55).astype(np.float32)


def synth_magic_ward(duration: float = 0.50) -> np.ndarray:
    """Crystalline cyan chord shimmer for Maren's blue glass bead & parry ward."""
    n = int(SAMPLE_RATE * duration)
    t = np.arange(n, dtype=np.float32) / SAMPLE_RATE
    chord = [1046.5, 1318.5, 1568.0, 2093.0]  # C6 major/add9 shimmer
    env = np.exp(-t * 6.5) * (1.0 - np.exp(-t * 80.0))
    sig = sum(np.sin(2.0 * math.pi * f * t + i * 0.5) * 0.25 for i, f in enumerate(chord))
    return (sig * env).astype(np.float32)


def synth_action_stinger() -> np.ndarray:
    """Crisp two-note power stinger marking STILL -> ACTION transition."""
    dur = 0.34
    n = int(SAMPLE_RATE * dur)
    t = np.arange(n, dtype=np.float32) / SAMPLE_RATE
    f = np.where(t < 0.12, 440.0, 659.25)  # A4 -> E5 power fifth
    phase = 2.0 * math.pi * np.cumsum(f) / SAMPLE_RATE
    sq = np.sign(np.sin(phase)) * 0.35 + np.sin(phase) * 0.45
    env = np.exp(-t * 7.5)
    return (sq * env).astype(np.float32)


def generate_full_soundtrack() -> Tuple[np.ndarray, np.ndarray, List[Dict[str, float]]]:
    """
    Generate the complete 45.0-second stereo audio buffer (int16, shape (N, 2)),
    a per-video-frame normalized amplitude envelope (shape (TOTAL_FRAMES,)),
    and a list of exact VO timing metadata dicts for VO_SCRIPT.md.
    """
    total_samples = int(round(TOTAL_DURATION * SAMPLE_RATE))
    stereo = np.zeros((total_samples, 2), dtype=np.float32)
    vo_Duck_mask = np.ones(total_samples, dtype=np.float32)
    vo_metadata: List[Dict[str, float]] = []

    # ========================================================================
    # 1. SYNTHESIZE & PLACE VOICEOVER NARRATION (DURING EACH SCENE'S STILL PHASE)
    # ========================================================================
    for scene in SCENES:
        vo_mono = _synth_flite_voice(scene.vo_text, voice="rms")
        vo_dur = len(vo_mono) / float(SAMPLE_RATE)
        # Ensure VO fits inside the STILL phase with a small cushion before STILL_END
        vo_start = scene.vo_start
        vo_end = min(scene.still_end - 0.12, vo_start + vo_dur)

        # Place main voice center + subtle stereo room taps (16ms L, 24ms R)
        _add_mono_to_stereo(stereo, vo_mono, vo_start, pan=0.0, gain=0.92)
        _add_mono_to_stereo(stereo, vo_mono, vo_start + 0.016, pan=-0.45, gain=0.11)
        _add_mono_to_stereo(stereo, vo_mono, vo_start + 0.024, pan=0.45, gain=0.11)

        # Duck music while VO is speaking
        s_idx = max(0, int((vo_start - 0.15) * SAMPLE_RATE))
        e_idx = min(total_samples, int((vo_end + 0.20) * SAMPLE_RATE))
        vo_Duck_mask[s_idx:e_idx] = 0.28

        # Add gentle typewriter clicks during VO text reveal
        num_clicks = min(28, len(scene.vo_text) // 3)
        click_dur = int(0.012 * SAMPLE_RATE)
        ct = np.arange(click_dur, dtype=np.float32) / SAMPLE_RATE
        click_wave = np.sin(2.0 * math.pi * 1150.0 * ct) * np.exp(-ct * 260.0) * 0.12
        for c_i in range(num_clicks):
            c_time = vo_start + (c_i / max(1, num_clicks)) * (vo_end - vo_start)
            _add_mono_to_stereo(stereo, click_wave, c_time, pan=-0.15 if c_i % 2 == 0 else 0.15, gain=0.8)

        # Add STILL -> ACTION transition stinger right at scene.still_end!
        stinger = synth_action_stinger()
        _add_mono_to_stereo(stereo, stinger, scene.still_end, pan=0.0, gain=0.65)

        vo_metadata.append(
            {
                "scene_id": scene.scene_id,
                "turn_id": scene.turn_id,
                "vo_start": vo_start,
                "vo_end": round(vo_start + vo_dur, 2),
                "still_end": scene.still_end,
                "scene_end": scene.end,
            }
        )

    # ========================================================================
    # 2. SCENE-SPECIFIC ACTION SOUND EFFECTS (DURING ACTION PHASES)
    # ========================================================================
    # Scene 1 Action (5.80s -> 11.50s): Footsteps, mule hoofbeats & 3 silver coin chimes
    s1 = SCENES[0]
    s1_act_len = s1.end - s1.still_end
    for step_i in range(10):
        st_time = s1.still_end + 0.15 + step_i * 0.26
        if st_time < s1.end - 0.3:
            n_st = int(0.045 * SAMPLE_RATE)
            tt = np.arange(n_st, dtype=np.float32) / SAMPLE_RATE
            step_snd = np.sin(2.0 * math.pi * (190.0 if step_i % 2 == 0 else 240.0) * tt) * np.exp(-tt * 75.0)
            _add_mono_to_stereo(stereo, step_snd, st_time, pan=-0.2 + step_i * 0.04, gain=0.28)

    for c_i, c_frac in enumerate([0.18, 0.34, 0.50]):
        launch_t = s1.still_end + c_frac * s1_act_len
        catch_t = launch_t + 0.32 * s1_act_len
        _add_mono_to_stereo(stereo, synth_coin_chime(0.35, 1.0 + c_i * 0.12), launch_t, pan=0.35, gain=0.42)
        _add_mono_to_stereo(stereo, synth_coin_chime(0.45, 1.25 + c_i * 0.15), catch_t, pan=0.05, gain=0.55)

    # Scene 2 Action (17.50s -> 25.00s): 4 Anvil Hammer Clangs, Blue Bead Blessing & Honed Blade Slash
    s2 = SCENES[1]
    s2_act_len = s2.end - s2.still_end
    for strike_i in range(4):
        strike_t = s2.still_end + (strike_i * 0.14 + 0.06) * s2_act_len
        _add_mono_to_stereo(stereo, synth_anvil_strike(), strike_t, pan=0.25, gain=0.72)

    # Elder Maren's blue glass bead blessing
    _add_mono_to_stereo(stereo, synth_magic_ward(0.60), s2.still_end + 0.28 * s2_act_len, pan=-0.35, gain=0.55)
    # Wren catching and slashing the honed short sword (peaking around t = 22.0s)
    _add_mono_to_stereo(stereo, synth_sword_slash(0.42, heavy=False), s2.still_end + 0.54 * s2_act_len, pan=0.0, gain=0.70)
    _add_mono_to_stereo(stereo, synth_sword_slash(0.48, heavy=True), 21.85, pan=0.1, gain=0.78)

    # Scene 3 Action (31.00s -> 39.50s): Dread-Wolf Ambush, Ward Parry, Twin Dash Combo & Moon Cleave!
    s3 = SCENES[2]
    s3_act_len = s3.end - s3.still_end
    # Beat 1: Wolf lunge growl + Ward Parry
    _add_mono_to_stereo(stereo, synth_wolf_growl(0.70), s3.still_end + 0.04 * s3_act_len, pan=0.35, gain=0.68)
    _add_mono_to_stereo(stereo, synth_magic_ward(0.50), s3.still_end + 0.16 * s3_act_len, pan=-0.15, gain=0.70)
    _add_mono_to_stereo(stereo, synth_anvil_strike(0.35), s3.still_end + 0.16 * s3_act_len, pan=-0.1, gain=0.45)

    # Beat 2: Counter-dash & twin slashes
    _add_mono_to_stereo(stereo, synth_sword_slash(0.35, heavy=False), s3.still_end + 0.36 * s3_act_len, pan=-0.1, gain=0.68)
    _add_mono_to_stereo(stereo, synth_sword_slash(0.38, heavy=False), s3.still_end + 0.50 * s3_act_len, pan=0.15, gain=0.72)

    # Beat 3: Climax Moonlit Cleave right around t = 38.0s!
    _add_mono_to_stereo(stereo, synth_wolf_growl(0.55), 36.75, pan=0.2, gain=0.60)
    _add_mono_to_stereo(stereo, synth_sword_slash(0.58, heavy=True), 37.65, pan=0.0, gain=0.92)
    _add_mono_to_stereo(stereo, synth_magic_ward(0.65), 37.90, pan=0.0, gain=0.75)
    _add_mono_to_stereo(stereo, synth_coin_chime(0.60, 1.4), 38.35, pan=0.1, gain=0.60)

    # Scene 4 Action (42.75s -> 45.00s): Dreaming Constellation Arpeggio & Finale Chord
    s4 = SCENES[3]
    arp_notes = [587.33, 659.25, 739.99, 880.0, 1174.66, 1479.98]  # D major/lydian dawn constellation
    for n_i, freq in enumerate(arp_notes):
        nt = s4.still_end + n_i * 0.22
        dur = 1.1
        n_samp = int(dur * SAMPLE_RATE)
        tt = np.arange(n_samp, dtype=np.float32) / SAMPLE_RATE
        bell = (np.sin(2.0 * math.pi * freq * tt) + 0.35 * np.sin(2.0 * math.pi * freq * 2.0 * tt)) * np.exp(-tt * 3.5)
        _add_mono_to_stereo(stereo, bell * 0.35, nt, pan=-0.4 + n_i * 0.16, gain=0.65)

    # ========================================================================
    # 3. ADAPTIVE 16-BIT CHIPTUNE & SYNTH SCORE (0.0s -> 45.0s)
    # ========================================================================
    # D Dorian scale frequencies: D, E, F, G, A, B, C
    bpm = 136.0
    step_sec = (60.0 / bpm) / 2.0  # Eighth-note grid (~0.2205s)
    num_steps = int(TOTAL_DURATION / step_sec)

    arp_pattern = [293.66, 349.23, 440.00, 587.33, 523.25, 440.00, 349.23, 329.63]
    lead_pattern = [587.33, 659.25, 698.46, 880.00, 783.99, 698.46, 659.25, 587.33]
    bass_pattern = [73.42, 73.42, 87.31, 98.00, 110.00, 110.00, 98.00, 87.31]

    music_stereo = np.zeros_like(stereo)
    for st in range(num_steps):
        st_time = st * step_sec
        if st_time >= TOTAL_DURATION:
            break
        scene_now, is_act_now, _ = (
            SCENES[0],
            False,
            0.0,
        )
        for sc in SCENES:
            if sc.start <= st_time < sc.end:
                scene_now = sc
                is_act_now = st_time >= sc.still_end
                break

        n_step = int(step_sec * SAMPLE_RATE)
        tt = np.arange(n_step, dtype=np.float32) / SAMPLE_RATE

        # Gentle 16-bit harp/lute arpeggio (always present)
        arp_f = arp_pattern[st % len(arp_pattern)]
        arp_wave = (
            np.sin(2.0 * math.pi * arp_f * tt) * 0.6
            + np.sign(np.sin(2.0 * math.pi * arp_f * tt)) * 0.15
        ) * np.exp(-tt * 9.5)
        _add_mono_to_stereo(music_stereo, arp_wave * 0.22, st_time, pan=-0.25 if st % 2 == 0 else 0.25, gain=1.0)

        # Bassline
        bass_f = bass_pattern[(st // 2) % len(bass_pattern)]
        bass_wave = np.tanh(np.sin(2.0 * math.pi * bass_f * tt) * 2.2) * np.exp(-tt * 5.0)
        _add_mono_to_stereo(music_stereo, bass_wave * (0.34 if is_act_now else 0.16), st_time, pan=0.0, gain=1.0)

        # Driving action drums + heroic chiptune lead during ACTION phases!
        if is_act_now:
            lead_f = lead_pattern[(st + scene_now.scene_id * 2) % len(lead_pattern)]
            lead_wave = (
                np.sign(np.sin(2.0 * math.pi * lead_f * tt)) * 0.28
                + np.sin(2.0 * math.pi * lead_f * tt) * 0.45
            ) * np.exp(-tt * 6.0)
            _add_mono_to_stereo(music_stereo, lead_wave * 0.24, st_time, pan=0.15, gain=1.0)

            # Kick on even steps, snare on odd steps
            if st % 2 == 0:
                kick = np.sin(2.0 * math.pi * (120.0 * np.exp(-tt * 32.0) + 45.0) * tt) * np.exp(-tt * 18.0)
                _add_mono_to_stereo(music_stereo, kick * 0.38, st_time, pan=0.0, gain=1.0)
            else:
                rng = np.random.default_rng(st)
                snare = rng.normal(0.0, 1.0, n_step).astype(np.float32) * np.exp(-tt * 26.0)
                _add_mono_to_stereo(music_stereo, snare * 0.20, st_time, pan=0.0, gain=1.0)

    # Apply sidechain ducking to music where VO is speaking
    stereo += music_stereo * vo_Duck_mask[:, None]

    # Smooth fade-in (first 0.25s) and fade-out (last 0.45s)
    fade_in_n = int(0.25 * SAMPLE_RATE)
    fade_out_n = int(0.45 * SAMPLE_RATE)
    stereo[:fade_in_n] *= np.linspace(0.0, 1.0, fade_in_n, dtype=np.float32)[:, None]
    stereo[-fade_out_n:] *= np.linspace(1.0, 0.0, fade_out_n, dtype=np.float32)[:, None]

    # Soft master limiter to prevent clipping
    stereo = np.tanh(stereo * 1.15) * 0.92
    pcm16 = (np.clip(stereo, -1.0, 1.0) * 32767.0).astype(np.int16)

    # Compute per-frame RMS amplitude envelope for the 60fps UI visualizer
    samples_per_frame = SAMPLE_RATE // FPS
    envelope = np.zeros(TOTAL_FRAMES, dtype=np.float32)
    mono_mix = np.mean(np.abs(stereo), axis=1)
    for f_i in range(TOTAL_FRAMES):
        s0 = f_i * samples_per_frame
        s1_idx = min(len(mono_mix), s0 + samples_per_frame)
        if s1_idx > s0:
            envelope[f_i] = float(np.sqrt(np.mean(mono_mix[s0:s1_idx] ** 2)))
    max_env = float(np.max(envelope))
    if max_env > 1e-5:
        envelope = np.clip(envelope / max_env, 0.1, 1.0)

    return pcm16, envelope, vo_metadata


def save_wav(path: str, pcm16: np.ndarray) -> None:
    """Write stereo int16 PCM array to a WAV file."""
    with wave.open(path, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm16.tobytes())
