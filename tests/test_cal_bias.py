"""Function-level tests of the real andes_cal_bias recipe.

The stacking/QC functions are tested directly on synthetic arrays with
known truth; the pyesorex/EDPS plumbing is exercised by the end-to-end
run on simulator data (see wkf_status.md).
"""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "recipes"))

from andes_cal_bias import clipped_mean_std, extension_qc, stack_extension


RNG = np.random.default_rng(42)


def synthetic_stack(n=10, shape=(64, 64), level=1000.0, ron=3.5):
    return RNG.normal(level, ron, size=(n, *shape)).astype(np.float32)


def test_clipped_mean_recovers_level_and_noise():
    stack = synthetic_stack()
    mean, std = clipped_mean_std(stack, kappa=5.0, iterations=3)
    assert mean.mean() == pytest.approx(1000.0, abs=0.5)
    # per-pixel sample std across the stack estimates the RON
    assert np.sqrt(np.mean(std.astype(float) ** 2)) == pytest.approx(3.5, rel=0.05)
    # master noise averages down ~sqrt(n)
    assert mean.std() == pytest.approx(3.5 / np.sqrt(10), rel=0.1)


def test_clipping_removes_outliers():
    stack = synthetic_stack()
    clean_mean, _ = clipped_mean_std(stack.copy(), kappa=5.0, iterations=3)
    # cosmic-ray-like hits on one frame
    hits = (RNG.random(stack.shape[1:]) < 0.01)
    stack[3][hits] += 50000.0
    mean, _ = clipped_mean_std(stack, kappa=5.0, iterations=3)
    assert np.abs(mean[hits] - clean_mean[hits]).max() < 5.0
    # without clipping the hits would shift those pixels by ~5000 ADU
    assert np.abs(stack.mean(axis=0)[hits] - clean_mean[hits]).min() > 1000.0


def test_identical_values_survive_clipping():
    stack = np.full((5, 8, 8), 100.0, dtype=np.float32)
    mean, std = clipped_mean_std(stack, kappa=5.0, iterations=3)
    assert np.all(mean == 100.0)
    assert np.all(std == 0.0)


def test_extension_qc_values():
    master = RNG.normal(1000.0, 1.1, size=(64, 64)).astype(np.float32)
    res = np.full((64, 64), 3.5, dtype=np.float32)
    qc = extension_qc("BIAS", master, res, gain=2.0)
    assert qc["ESO QC BIAS LEVEL"] == pytest.approx(1000.0, abs=0.5)
    assert qc["ESO QC BIAS RON ADU"] == pytest.approx(3.5, abs=0.01)
    assert qc["ESO QC BIAS RON E"] == pytest.approx(7.0, abs=0.02)
    assert qc["ESO QC BIAS MASTER RMS"] == pytest.approx(1.1, rel=0.1)


def test_stack_extension_reads_mef_blocks(tmp_path):
    from astropy.io import fits
    paths = []
    for i in range(4):
        hdul = fits.HDUList([fits.PrimaryHDU()])
        data = RNG.normal(1000.0, 3.5, size=(96, 32))
        hdul.append(fits.ImageHDU(np.clip(np.rint(data), 0, 65535).astype(np.uint16),
                                  name="R"))
        p = tmp_path / f"bias_{i}.fits"
        hdul.writeto(p)
        paths.append(str(p))

    import andes_cal_bias
    old_block = andes_cal_bias.BLOCK_ROWS
    andes_cal_bias.BLOCK_ROWS = 40  # force several partial blocks
    try:
        mean, std = stack_extension(paths, "R", kappa=5.0, iterations=3)
    finally:
        andes_cal_bias.BLOCK_ROWS = old_block
    assert mean.shape == (96, 32)
    assert mean.mean() == pytest.approx(1000.0, abs=1.0)
    assert np.sqrt(np.mean(std.astype(float) ** 2)) == pytest.approx(3.5, rel=0.15)
