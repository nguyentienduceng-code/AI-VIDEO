"""
Test hồi quy cho Literary Mode SFX:
1. get_literary_sfx() chọn đúng config theo genre
2. adjust_sfx_for_scene_duration() nhân gain theo scene duration
3. _mix_audio_tracks nhận tuple 8-phần tử (fade_in_ms, fade_out_ms)

Chạy:  python tests/test_literary_sfx.py    (từ backend/)
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import soundfile as sf

from services.video_service import (
    get_literary_sfx,
    adjust_sfx_for_scene_duration,
    _mix_audio_tracks,
    LITERARY_SFX_MAP,
    SCENE_SFX_GAIN,
)

SR = 44100
_TMP = tempfile.mkdtemp(prefix="literary_sfx_test_")


def _wav(name: str, seconds: float, amp: float = 1.0) -> str:
    path = os.path.join(_TMP, name)
    data = np.full((max(1, int(seconds * SR)), 2), amp, dtype=np.float32)
    sf.write(path, data, SR)
    return path


# ── 1. get_literary_sfx() chọn đúng genre ─────────────────────────────────
def test_get_literary_sfx_fiction():
    cfg = get_literary_sfx("fiction")
    assert cfg["sfx_name"] == "bell", cfg
    assert cfg["genre"] == "fiction"
    assert "gain_boost" in cfg
    assert "fade_in_ms" in cfg
    assert "fade_out_ms" in cfg


def test_get_literary_sfx_thriller():
    cfg = get_literary_sfx("thriller")
    assert cfg["sfx_name"] == "heartbeat", cfg
    assert cfg["genre"] == "thriller"


def test_get_literary_sfx_unknown_defaults_to_selfhelp():
    cfg = get_literary_sfx("unknown_genre")
    assert cfg["sfx_name"] == "pop", cfg  # selfhelp primary


def test_get_literary_sfx_all_genres_present():
    genres = ["fiction", "philosophy", "thriller", "spiritual", "poetry", "raw_truth", "selfhelp", "business"]
    for genre in genres:
        cfg = get_literary_sfx(genre)
        assert genre in LITERARY_SFX_MAP, f"Missing genre: {genre}"
        assert cfg["gain_boost"] == 1.0, f"{genre}: gain_boost must be 1.0 (Path 1 RMS-calibrated)"
        assert "fade_in_ms" in cfg and "fade_out_ms" in cfg


def test_get_literary_sfx_fade_values_vary_by_genre():
    spiritual = get_literary_sfx("spiritual")
    thriller = get_literary_sfx("thriller")
    # Spiritual: fade dài (100/150ms), Thriller: fade ngắn (20/100ms)
    assert spiritual["fade_in_ms"] > thriller["fade_in_ms"], "Spiritual should have longer fade-in"


# ── 2. adjust_sfx_for_scene_duration() ──────────────────────────────────────
def test_short_scene_reduces_gain():
    base = 1.0
    result = adjust_sfx_for_scene_duration("bell.wav", 2.0, base)
    assert result < base, f"Short scene (<3s) should reduce gain, got {result}"


def test_long_scene_boosts_gain():
    base = 1.0
    result = adjust_sfx_for_scene_duration("bell.wav", 6.0, base)
    assert result > base, f"Long scene (>5s) should boost gain, got {result}"


def test_medium_scene_keeps_gain():
    base = 1.0
    result = adjust_sfx_for_scene_duration("bell.wav", 4.0, base)
    assert result == base, f"Medium scene (3-5s) should keep gain, got {result}"


def test_gain_boost_multiplies_with_duration():
    base = 1.0
    boost = 1.2
    short = adjust_sfx_for_scene_duration("bell.wav", 2.0, base, boost)
    long = adjust_sfx_for_scene_duration("bell.wav", 6.0, base, boost)
    assert short < long, "Boost should apply on top of duration multiplier"


# ── 3. _mix_audio_tracks nhận tuple 8-phần tử ────────────────────────────
def test_mix_accepts_8_element_tuple_with_fade():
    """Placement tuple: (path, start, volume, fadeout, max_dur, pitch, fade_in_ms, fade_out_ms)"""
    voice = _wav("v.wav", 2.0, 0.5)
    sfx = _wav("s.wav", 0.3, 0.8)

    # 8-element tuple: fade_in_ms=50, fade_out_ms=30
    placements = [
        (voice, 0.0, 1.0, 0.05),
        (sfx, 0.5, 0.6, 0.0, None, 1.0, 50, 30),
    ]
    result, sr = _mix_audio_tracks(placements, 2.5, SR, return_array=True)
    assert result is not None, "Should return audio array with fade envelope"
    assert sr == SR


def test_mix_backward_compatible_6_element_tuple():
    """6-element tuple (không có fade_in_ms, fade_out_ms) phải vẫn hoạt động."""
    voice = _wav("v.wav", 2.0, 0.5)
    sfx = _wav("s.wav", 0.3, 0.8)

    # 6-element tuple: (path, start, volume, fadeout, max_dur, pitch)
    placements = [
        (voice, 0.0, 1.0, 0.05),
        (sfx, 0.5, 0.6, 0.0, None, 1.0),
    ]
    result, sr = _mix_audio_tracks(placements, 2.5, SR, return_array=True)
    assert result is not None, "Should work with 6-element tuple (backward compat)"


# ── 4. SCENE_SFX_GAIN entries tồn tại cho Literary files ──────────────────
def test_scene_sfx_gain_has_bell_chime():
    assert "bell_chime" in SCENE_SFX_GAIN, f"Missing bell_chime in SCENE_SFX_GAIN: {list(SCENE_SFX_GAIN.keys())}"


def test_scene_sfx_gain_has_heartbeat_dramatic():
    assert "heartbeat_dramatic" in SCENE_SFX_GAIN, f"Missing heartbeat_dramatic: {list(SCENE_SFX_GAIN.keys())}"


def test_scene_sfx_gain_values_are_reasonable():
    """Tất cả gain phải trong khoảng 0.1 - 5.0."""
    for name, gain in SCENE_SFX_GAIN.items():
        assert 0.1 <= gain <= 5.0, f"{name}: gain={gain} out of range [0.1, 5.0]"


# ── Run all ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import traceback

    tests = [
        test_get_literary_sfx_fiction,
        test_get_literary_sfx_thriller,
        test_get_literary_sfx_unknown_defaults_to_selfhelp,
        test_get_literary_sfx_all_genres_present,
        test_get_literary_sfx_fade_values_vary_by_genre,
        test_short_scene_reduces_gain,
        test_long_scene_boosts_gain,
        test_medium_scene_keeps_gain,
        test_gain_boost_multiplies_with_duration,
        test_mix_accepts_8_element_tuple_with_fade,
        test_mix_backward_compatible_6_element_tuple,
        test_scene_sfx_gain_has_bell_chime,
        test_scene_sfx_gain_has_heartbeat_dramatic,
        test_scene_sfx_gain_values_are_reasonable,
    ]

    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR {t.__name__}: {e}")
            failed += 1

    print(f"\n{'='*50}")
    print(f"Results: {passed}/{passed+failed} passed")
    if failed:
        print(f"FAILED: {failed}")
        sys.exit(1)
    else:
        print("All tests passed!")
        sys.exit(0)
