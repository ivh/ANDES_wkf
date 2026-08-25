"""Function-level tests of the real andes_util_detcal recipe.

The cleaning is tested on synthetic detector frames built from the same
forward model the E2E simulator uses:
    adu = electrons/gain + bias + N(0, ron_adu),  electrons = signal + dark*t
so the truth (signal in electrons) is known. The pyesorex/EDPS plumbing is
exercised by the end-to-end cascade run (see wkf_status.md).
"""

import os
import sys
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits

sys.path.insert(0, str(Path(__file__).parent.parent / "recipes"))

from andes_util_detcal import (  # noqa: E402
    GAIN_KEY, RON_KEY, QUAL_BADPIX, QUAL_HOTPIX, QUAL_SATURATED,
    base_tag, clean_band, clean_frame)

RNG = np.random.default_rng(7)
GAIN = 2.0        # e-/ADU (CCD fast, matches the simulator)
BIAS = 1000.0
RON_E = 7.0
SHAPE = (128, 128)


def raw_frame(signal_e, exptime=0.0, dark_e_s=0.0):
    """Simulator forward model -> raw ADU (float, unrounded)."""
    electrons = signal_e + dark_e_s * exptime
    adu = electrons / GAIN + BIAS
    adu = adu + RNG.normal(0.0, RON_E / GAIN, size=adu.shape)
    return adu.astype(np.float32)


def test_recovers_signal_in_electrons():
    signal = np.full(SHAPE, 500.0, dtype=np.float32)          # 500 e-
    adu = raw_frame(signal)
    bias = np.full(SHAPE, BIAS, dtype=np.float32)
    data, err, qual = clean_band(adu, GAIN, RON_E, exptime=0.0, bias=bias)
    assert np.median(data) == pytest.approx(500.0, abs=2.0)
    # error ~ sqrt(signal + ron^2)
    assert np.median(err) == pytest.approx(np.sqrt(500.0 + RON_E ** 2), rel=0.05)
    assert not qual.any()


def test_dark_subtraction_scales_with_exptime():
    exptime, dark_rate = 1800.0, 0.02                          # NIR-like
    signal = np.full(SHAPE, 100.0, dtype=np.float32)
    adu = raw_frame(signal, exptime=exptime, dark_e_s=dark_rate)
    bias = np.full(SHAPE, BIAS, dtype=np.float32)
    dark = np.full(SHAPE, dark_rate, dtype=np.float32)         # e-/s map
    data, _, _ = clean_band(adu, GAIN, RON_E, exptime, bias=bias, dark_rate=dark)
    assert np.median(data) == pytest.approx(100.0, abs=3.0)
    # without dark subtraction the level would be off by dark*t = 36 e-
    no_dark, _, _ = clean_band(adu, GAIN, RON_E, exptime, bias=bias)
    assert np.median(no_dark) == pytest.approx(100.0 + dark_rate * exptime, abs=3.0)


def test_flat_field_divides_out_prnu():
    prnu = RNG.normal(1.0, 0.02, SHAPE).astype(np.float32)
    signal = (300.0 * prnu).astype(np.float32)                 # response-scaled
    adu = raw_frame(signal)
    bias = np.full(SHAPE, BIAS, dtype=np.float32)
    flat, _, _ = clean_band(adu, GAIN, RON_E, 0.0, bias=bias, flat=prnu)
    noflat, _, _ = clean_band(adu, GAIN, RON_E, 0.0, bias=bias)
    assert flat.std() < noflat.std()                            # PRNU removed
    assert np.median(flat) == pytest.approx(300.0, abs=3.0)


def test_quality_flags_saturation_and_masks():
    adu = raw_frame(np.full(SHAPE, 100.0, dtype=np.float32))
    adu[0, 0] = 70000.0                                        # saturated
    badpix = np.zeros(SHAPE, dtype=np.int32); badpix[1, 1] = 1
    hotpix = np.zeros(SHAPE, dtype=np.int32); hotpix[2, 2] = 1
    _, _, qual = clean_band(adu, GAIN, RON_E, 0.0, badpix=badpix, hotpix=hotpix)
    assert qual[0, 0] & QUAL_SATURATED
    assert qual[1, 1] & QUAL_BADPIX
    assert qual[2, 2] & QUAL_HOTPIX
    assert np.count_nonzero(qual) == 3


def test_missing_calibrations_are_skipped():
    # no bias -> data still in electrons, just offset by the bias level
    adu = raw_frame(np.full(SHAPE, 0.0, dtype=np.float32))
    data, err, qual = clean_band(adu, GAIN, RON_E, 0.0)
    assert np.median(data) == pytest.approx(BIAS * GAIN, abs=5.0)
    assert not qual.any()


def test_clean_frame_reads_mef_and_uses_per_ext_gain(tmp_path):
    from astropy.io import fits
    hdul = fits.HDUList([fits.PrimaryHDU()])
    hdul[0].header["EXPTIME"] = 0.0
    signal = np.full((64, 64), 250.0, dtype=np.float32)
    ext = fits.ImageHDU(raw_frame(signal), name="R")
    ext.header["HIERARCH ESO DET CHIP GAIN"] = GAIN
    ext.header["HIERARCH ESO DET CHIP RON"] = RON_E
    hdul.append(ext)
    p = tmp_path / "raw.fits"
    hdul.writeto(p)

    calibs = {k: {} for k in ("bias", "res", "dark", "flat", "badpix", "hotpix")}
    calibs["bias"] = {"R": np.full((64, 64), BIAS, dtype=np.float32)}
    result = clean_frame(str(p), calibs)
    assert set(result) == {"R"}
    data, err, qual = result["R"]
    assert np.median(data) == pytest.approx(250.0, abs=2.0)


def test_base_tag_from_group():
    assert base_tag(["FLAT_A", "FLAT_B"]) == "FLAT"
    assert base_tag(["DARK"]) == "DARK"
    assert base_tag(["ORDERDEF_A", "ORDERDEF_B"]) == "ORDERDEF"


# --- real-frame closed loop (skipped unless the E2E simulator night exists) ---
# Complements the synthetic tests above: exercises the true MEF layout, real
# noise, uint16 rounding and the actual clean_frame path on simulator pixels.
# Override the location with $ANDES_RAWNIGHTS.

RAWNIGHTS = Path(os.environ.get("ANDES_RAWNIGHTS", Path.home() / "ANDES/E2E/rawnights"))


def _find_frame(dpr_type):
    if not RAWNIGHTS.exists():
        return None
    for path in sorted(RAWNIGHTS.rglob("*.fits")):
        try:
            header = fits.getheader(path)
        except OSError:
            continue
        if header.get("HIERARCH ESO DPR TYPE") == dpr_type and len(fits.open(path)) > 1:
            return path
    return None


BIAS_FRAME = _find_frame("BIAS")


@pytest.mark.skipif(BIAS_FRAME is None,
                    reason=f"no simulator BIAS frame under {RAWNIGHTS}")
def test_closed_loop_on_real_bias_frame():
    """Cleaning a real BIAS frame with a median master bias -> ~0 e-, std ~RON."""
    with fits.open(BIAS_FRAME) as hdul:
        band = hdul[1].name
        raw = hdul[1].data.astype(np.float32)
        gain = float(hdul[1].header[GAIN_KEY])
        ron = float(hdul[1].header[RON_KEY])

    calibs = {k: {} for k in ("bias", "res", "dark", "flat", "badpix", "hotpix")}
    calibs["bias"] = {band: np.full(raw.shape, np.median(raw), dtype=np.float32)}
    data, err, qual = clean_frame(str(BIAS_FRAME), calibs)[band]

    assert np.median(data) == pytest.approx(0.0, abs=0.5)   # bias removed
    assert np.std(data) == pytest.approx(ron, rel=0.1)      # residual = read noise
    assert np.median(err) == pytest.approx(ron, rel=0.1)    # err map ~ RON at ~0 signal
    assert gain > 0
