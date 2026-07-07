"""andes_cal_bias: master bias from a stack of raw BIAS frames.

First real recipe (replaces its dummy); its conventions are the template
for the others:
- products mirror the raw MEF layout (DRL 4.1): DFS-compliant header-only
  primary carrying PRO.CATG, the setup keywords and summary QC; one
  float32 image extension per detector of the arm with per-extension QC
- MASTER_BIAS is the kappa-sigma-clipped per-pixel mean of the stack;
  MASTER_BIAS_RES the per-pixel standard deviation across the clipped
  stack (a read-noise map, and the residual reference for CALCHECKER)
- QC per extension: QC BIAS LEVEL [ADU], QC BIAS RON [ADU] and
  QC BIAS RON E (using the extension's gain keyword), QC BIAS MASTER RMS
  [ADU]; QC BIAS NFRAMES on the primary

Processing is block-wise over detector rows: a full RIZ stack would
otherwise hold 10 x 2 x 85 Mpx in memory.
"""

import cpl
import numpy as np
from astropy.io import fits

PIPE_ID = "andes/0.1"

# keywords forwarded so products match on the instrument setup
SETUP_KEYS = ["INSTRUME", "MJD-OBS", "HIERARCH ESO SEQ ARM", "HIERARCH ESO INS MODE",
              "HIERARCH ESO DET BINX", "HIERARCH ESO DET BINY",
              "HIERARCH ESO DET READOUT", "HIERARCH ESO TPL START"]

GAIN_KEY = "HIERARCH ESO DET CHIP GAIN"

BLOCK_ROWS = 512


def clipped_mean_std(stack, kappa, iterations):
    """Per-pixel kappa-sigma-clipped mean and std over axis 0.

    The clipping threshold uses the MAD-based sigma: the plain std is so
    inflated by a single strong outlier (cosmic hit) in a small stack
    that kappa*std would never catch it. Returns (mean, std) of the
    surviving frames, std with ddof=1.
    """
    data = np.ma.MaskedArray(stack, mask=np.zeros(stack.shape, dtype=bool))
    for _ in range(iterations):
        center = np.ma.median(data, axis=0)
        mad_sigma = 1.4826 * np.ma.median(np.ma.abs(data - center[np.newaxis]),
                                          axis=0)
        # a pixel whose surviving values are identical has spread 0; keep it
        limit = kappa * np.ma.maximum(mad_sigma, 1e-3)
        new_mask = np.ma.abs(data - center[np.newaxis]) > limit[np.newaxis]
        if not new_mask.any():
            break
        data.mask |= new_mask.filled(False)
    mean = data.mean(axis=0)
    std = data.std(axis=0, ddof=1)
    return (np.asarray(mean.filled(0), dtype=np.float32),
            np.asarray(std.filled(0), dtype=np.float32))


def stack_extension(paths, ext, kappa, iterations):
    """Block-wise clipped stack of one detector extension of all frames."""
    with fits.open(paths[0]) as hdul:
        ny, nx = hdul[ext].data.shape
    mean = np.empty((ny, nx), dtype=np.float32)
    std = np.empty((ny, nx), dtype=np.float32)

    handles = [fits.open(p) for p in paths]
    try:
        for y0 in range(0, ny, BLOCK_ROWS):
            y1 = min(y0 + BLOCK_ROWS, ny)
            block = np.stack([h[ext].section[y0:y1, :].astype(np.float32)
                              for h in handles])
            mean[y0:y1], std[y0:y1] = clipped_mean_std(block, kappa, iterations)
    finally:
        for h in handles:
            h.close()
    return mean, std


def extension_qc(prefix, master, res, gain):
    """QC values for one detector extension."""
    level = float(np.median(master))
    # sqrt(mean(s^2)) is an unbiased noise estimate; median-of-std is not
    ron_adu = float(np.sqrt(np.mean(res.astype(np.float64) ** 2)))
    qc = {
        f"ESO QC {prefix} LEVEL": level,
        f"ESO QC {prefix} RON ADU": ron_adu,
        f"ESO QC {prefix} MASTER RMS": float(np.std(master)),
    }
    if gain is not None:
        qc[f"ESO QC {prefix} RON E"] = ron_adu * gain
    return qc


def save_mef_product(catg, filename, arrays, ext_qc, ext_gains,
                     primary_qc, frameset, parameters, recipe_name,
                     setup_header):
    """DFS primary via cpl.dfs, detector extensions via astropy."""
    applist = cpl.core.PropertyList()
    applist.append(cpl.core.Property("ESO PRO CATG", catg))
    for key in SETUP_KEYS:
        if key in setup_header:
            applist.append(cpl.core.Property(key, setup_header[key]))
    for key, value in primary_qc.items():
        applist.append(cpl.core.Property(key, value))

    cpl.dfs.save_propertylist(frameset, parameters, frameset, recipe_name,
                              applist, PIPE_ID, filename)

    with fits.open(filename, mode="append") as hdul:
        for band, image in arrays.items():
            hdr = fits.Header()
            hdr["BUNIT"] = "ADU"
            if ext_gains.get(band) is not None:
                hdr[GAIN_KEY] = ext_gains[band]
            for key, value in ext_qc[band].items():
                hdr[key] = value
            hdul.append(fits.ImageHDU(image, header=hdr, name=band))

    return cpl.ui.Frame(filename, tag=catg,
                        group=cpl.ui.Frame.FrameGroup.PRODUCT)


class AndesCalBias(cpl.ui.PyRecipe):
    _name = "andes_cal_bias"
    _version = "0.2"
    _author = "ANDES DRS team"
    _email = "thomas.marquart@physics.uu.se"
    _copyright = "GPL-3.0-or-later"
    _synopsis = "Master bias from a stack of raw BIAS frames"
    _description = (
        "Kappa-sigma-clipped per-pixel mean of the BIAS frames per detector "
        "extension. Products: MASTER_BIAS (clipped mean) and MASTER_BIAS_RES "
        "(per-pixel std across the stack, a read-noise map), both MEF files "
        "mirroring the raw layout, with per-extension level/RON QC.")

    def __init__(self):
        self.parameters = cpl.ui.ParameterList([
            cpl.ui.ParameterValue("andes_cal_bias.kappa",
                                  "Kappa-sigma clipping threshold",
                                  "andes_cal_bias", 5.0),
            cpl.ui.ParameterValue("andes_cal_bias.clip_iterations",
                                  "Clipping iterations",
                                  "andes_cal_bias", 3),
        ])

    def run(self, frameset, settings):
        for name, value in settings.items():
            if name in [p.name for p in self.parameters]:
                self.parameters[name].value = value
        kappa = float(self.parameters["andes_cal_bias.kappa"].value)
        iterations = int(self.parameters["andes_cal_bias.clip_iterations"].value)

        raw = [f for f in frameset if f.tag == "BIAS"] or list(frameset)
        if len(raw) < 2:
            raise cpl.core.DataNotFoundError(
                f"andes_cal_bias needs at least 2 BIAS frames, got {len(raw)}")
        for frame in frameset:
            frame.group = (cpl.ui.Frame.FrameGroup.RAW if frame in raw
                           else cpl.ui.Frame.FrameGroup.CALIB)
        paths = [f.file for f in raw]

        setup_header = fits.getheader(paths[0])
        with fits.open(paths[0]) as hdul:
            bands = [h.name for h in hdul[1:] if h.is_image]
            gains = {h.name: h.header.get(GAIN_KEY) for h in hdul[1:]}

        masters, residuals, ext_qc = {}, {}, {}
        for band in bands:
            master, res = stack_extension(paths, band, kappa, iterations)
            masters[band] = master
            residuals[band] = res
            ext_qc[band] = extension_qc("BIAS", master, res, gains.get(band))

        primary_qc = {"ESO QC BIAS NFRAMES": len(raw)}
        products = cpl.ui.FrameSet()
        products.append(save_mef_product(
            "MASTER_BIAS", "master_bias.fits", masters, ext_qc, gains,
            primary_qc, frameset, self.parameters, self._name, setup_header))
        res_qc = {band: {} for band in bands}
        products.append(save_mef_product(
            "MASTER_BIAS_RES", "master_bias_res.fits", residuals, res_qc,
            gains, primary_qc, frameset, self.parameters, self._name,
            setup_header))
        return products
