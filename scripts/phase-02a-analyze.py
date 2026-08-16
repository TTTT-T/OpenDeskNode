#!/usr/bin/env python3
"""Phase 2A objective audio metrics from the captured WAV files.

Computes:
  * MIC0/MIC1 independence: bit-identity ratio, windowed Pearson correlation
    (max over 500 ms windows), and the inter-channel delay from the
    cross-correlation peak. A copied channel has identity 1.0 and r == 1.0.
  * AEC reference validity: windowed correlation between the playback
    reference channel and the raw mic during stimulus-active windows, plus
    the ref->mic delay.
  * ERLE: windowed 10*log10(P_raw/P_aec) between aec_off.wav and aec_on.wav
    after sub-sample-free alignment by cross-correlation, restricted to
    windows where the reference is active (echo present).

Emits a JSON result plus a human summary; exit code 0 iff all checks pass.
"""
import argparse
import json
import sys
import wave
from pathlib import Path

import numpy as np

WINDOW_MS = 500


def read_wav(path: Path):
    with wave.open(str(path), "rb") as w:
        assert w.getsampwidth() == 2 and w.getframerate() == 16000, path
        n = w.getnframes()
        raw = np.frombuffer(w.readframes(n), dtype="<i2").astype(np.float64)
        if w.getnchannels() == 2:
            return raw[0::2], raw[1::2]
        return raw, None


def windows(n: int, win: int):
    for start in range(0, n - win + 1, win):
        yield start, start + win


def pearson(a: np.ndarray, b: np.ndarray) -> float:
    a = a - a.mean()
    b = b - b.mean()
    denom = np.sqrt((a * a).sum() * (b * b).sum())
    if denom == 0:
        return 0.0
    return float((a * b).sum() / denom)


def max_windowed_r(x: np.ndarray, y: np.ndarray, rate: int) -> float:
    win = rate * WINDOW_MS // 1000
    best = 0.0
    for lo, hi in windows(min(len(x), len(y)), win):
        r = pearson(x[lo:hi], y[lo:hi])
        best = max(best, abs(r))
    return best


def min_window_residual(x: np.ndarray, y: np.ndarray, rate: int) -> float:
    """Minimum over 500 ms windows of the linear-fit residual energy ratio
    (1 - r^2). A digital copy of a channel yields exactly 0.0 in every
    window; two physical microphones always keep a nonzero residual from
    independent ADC noise and differing acoustic paths."""
    win = rate * WINDOW_MS // 1000
    best = 1.0
    for lo, hi in windows(min(len(x), len(y)), win):
        a = x[lo:hi]
        b = y[lo:hi]
        if (a * a).sum() == 0 or (b * b).sum() == 0:
            continue
        r = pearson(a, b)
        best = min(best, max(0.0, 1.0 - r * r))
    return best


def activity_ratio_db(ref: np.ndarray, rate: int) -> float:
    """Level contrast between playback and the 1 s silent lead-in."""
    lead = ref[:rate]
    active = ref[rate : 2 * rate]
    lead_rms = float(np.sqrt((lead**2).mean()))
    active_rms = float(np.sqrt((active**2).mean()))
    if lead_rms <= 0.0:
        return 999.0
    return 10.0 * np.log10(active_rms / lead_rms)


def xcorr_delay(ref: np.ndarray, mic: np.ndarray, rate: int, max_ms: float = 40.0):
    """Delay (samples, mic relative to ref) of the cross-correlation peak."""
    n = min(len(ref), len(mic))
    max_lag = int(rate * max_ms / 1000)
    a = ref[:n] - ref[:n].mean()
    b = mic[:n] - mic[:n].mean()
    size = 1
    while size < 2 * n:
        size <<= 1
    fa = np.fft.rfft(a, size)
    fb = np.fft.rfft(b, size)
    corr = np.fft.irfft(fb * np.conj(fa), size)
    lags = np.concatenate((np.arange(0, max_lag + 1), np.arange(-max_lag, 0)))
    vals = np.concatenate((corr[: max_lag + 1], corr[-max_lag:]))
    peak = int(lags[int(np.argmax(np.abs(vals)))])
    return peak


def active_mask(ref: np.ndarray, rate: int) -> np.ndarray:
    """True where the reference energy in this 10 ms bin is well above the
    silent lead-in floor (the lead-in is exactly 1 s of silence)."""
    bin_n = rate // 100
    bins = len(ref) // bin_n
    floor = np.sqrt((ref[: rate].astype(np.float64) ** 2).mean())
    mask = np.zeros(bins, dtype=bool)
    for i in range(bins):
        seg = ref[i * bin_n : (i + 1) * bin_n]
        mask[i] = np.sqrt((seg**2).mean()) > max(8.0 * floor, 1.0)
    return mask


def window_erle(raw: np.ndarray, out: np.ndarray, ref_active: np.ndarray, rate: int, lag: int):
    win = rate * WINDOW_MS // 1000
    bin_n = rate // 100
    results = []
    n = min(len(raw), len(out), len(ref_active) * bin_n)
    for lo, hi in windows(n, win):
        mid = (lo + hi) // 2
        if not ref_active[mid // bin_n]:
            continue
        p_raw = (raw[lo:hi] ** 2).mean()
        p_out = (out[lo + lag : hi + lag] ** 2).mean() if 0 <= lo + lag and hi + lag <= len(out) else (out[lo:hi] ** 2).mean()
        if p_raw > 1.0:
            results.append(10.0 * np.log10(p_raw / max(p_out, 1.0)))
    return results


def analyze(out_dir: Path) -> dict:
    mic0, mic1 = read_wav(out_dir / "mic0_mic1.wav")
    aec_off, _ = read_wav(out_dir / "aec_off.wav")
    aec_on, _ = read_wav(out_dir / "aec_on.wav")
    ref, _ = read_wav(out_dir / "playback_reference.wav")
    rate = 16000

    identity = float(np.mean(mic0[: min(len(mic0), len(mic1))] == mic1[: min(len(mic0), len(mic1))]))
    r_mics = max_windowed_r(mic0, mic1, rate)
    delay_mics = xcorr_delay(mic0, mic1, rate)
    residual_mics = min_window_residual(mic0, mic1, rate)

    r_ref = max_windowed_r(ref[: len(aec_off)], aec_off[: len(ref)], rate)
    delay_ref = xcorr_delay(ref, aec_off, rate)
    ref_activity_db = activity_ratio_db(ref, rate)

    lag = xcorr_delay(aec_off, aec_on, rate)
    ref_active = active_mask(ref, rate)
    erles = window_erle(aec_off, aec_on, ref_active, rate, lag)

    result = {
        "mic_independence": {
            "bit_identity_ratio": identity,
            "max_windowed_pearson": r_mics,
            "min_window_residual_ratio": residual_mics,
            "inter_mic_delay_samples": delay_mics,
            "independent": bool(identity < 0.5 and residual_mics > 1e-7),
        },
        "reference_validity": {
            "max_windowed_pearson_vs_mic": r_ref,
            "ref_mic_delay_samples": delay_ref,
            "ref_activity_ratio_db": ref_activity_db,
            "valid": bool(r_ref > 0.3 and ref_activity_db > 20.0),
        },
        "aec": {
            "alignment_lag_samples": lag,
            "erle_windows": len(erles),
            "erle_mean_db": float(np.mean(erles)) if erles else 0.0,
            "erle_min_db": float(np.min(erles)) if erles else 0.0,
            "erle_max_db": float(np.max(erles)) if erles else 0.0,
            "passed": bool(erles) and float(np.mean(erles)) >= 10.0,
        },
        "levels": {
            "mic0_rms": float(np.sqrt((mic0**2).mean())),
            "mic1_rms": float(np.sqrt((mic1**2).mean())),
            "ref_rms": float(np.sqrt((ref**2).mean())),
            "aec_off_rms": float(np.sqrt((aec_off**2).mean())),
            "aec_on_rms": float(np.sqrt((aec_on**2).mean())),
        },
    }
    result["passed"] = (
        result["mic_independence"]["independent"]
        and result["reference_validity"]["valid"]
        and result["aec"]["passed"]
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", required=True, type=Path)
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args()

    result = analyze(args.dir)
    if args.json_out:
        args.json_out.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
