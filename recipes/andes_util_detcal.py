"""andes_util_detcal: apply detector-signature corrections to any raw frame.

Second real recipe. Cleans each raw exposure of a group and produces, per
detector extension, a calibrated image in electrons with an error map and a
bad-pixel quality mask (DATA / <band>_ERR / <band>_QUAL). Two products,
keeping the tags the downstream tasks consume:

  <base>_DETCAL        one MEF per input exposure (individual cleaned frames)
  <base>_DETCAL_STACK  one MEF, mean-combined over the exposures

<base> is the common classification of the input group (DARK, FLAT, ...).

Corrections inverted from the raw forward model
    adu = electrons/gain + bias + N(0, ron);  electrons = signal + dark*t
are, each skipped unless the calibration is present with a matching shape
(so an absent/optional or a still-dummy calibration is simply ignored):

  bias subtract (MASTER_BIAS) -> gain to electrons (per-ext DET CHIP GAIN)
  -> dark subtract (MASTER_DARK, an e-/s rate map, x EXPTIME)
  -> flat-field (DETFLAT, normalised) -> bad-pixel flags
     (BAD_PIXEL_MASK | HOT_PIXEL_MASK, plus saturation).

Read noise for the error map comes from MASTER_BIAS_RES (per-pixel ADU std
x gain) when available, else the scalar DET CHIP RON. Linearity (the
simulator is linear), cosmic-ray rejection and swapped-frame (ABBA)
subtraction are not implemented yet -- see TODOs.

Header-only inputs (no image extensions) yield extension-less products, so
the EDPS cascade still flows; real validation is function-level against the
simulator forward model (tests/test_util_detcal.py).
"""

import cpl
import numpy as np
from astropy.io import fits

PIPE_ID = "andes/0.1"

SETUP_KEYS = ["INSTRUME", "MJD-OBS", "EXPTIME", "HIERARCH ESO SEQ ARM",
              "HIERARCH ESO INS MODE", "HIERARCH ESO DET BINX",
              "HIERARCH ESO DET BINY", "HIERARCH ESO DET READOUT",
              "HIERARCH ESO TPL START"]

GAIN_KEY = "HIERARCH ESO DET CHIP GAIN"
RON_KEY = "HIERARCH ESO DET CHIP RON"

# calibrations associated into a detcal job; everything else in the SOF is
# a raw frame of the group to be cleaned
DETCAL_CALIBS = {"MASTER_BIAS", "MASTER_BIAS_RES", "MASTER_DARK", "HOT_PIXEL_MASK",
                 "BAD_PIXEL_MASK", "DETFLAT", "DETLIN"}
MAIN_SUFFIXES = ("_DETCAL_STACK", "_DETCAL", "_BKGR_SUB")

# QUAL bitmask
QUAL_BADPIX = 1
QUAL_HOTPIX = 2
QUAL_SATURATED = 4

SATURATION_ADU = 65535.0


def strip_suffix(tag):
    for suffix in MAIN_SUFFIXES:
        if tag.endswith(suffix):
            return tag[: -len(suffix)]
    return tag


def base_tag(tags):
    import os
    prefix = os.path.commonprefix(sorted(set(tags)))
    return prefix.rstrip("_,") or "FRAME"


def clean_band(adu, gain, ron_e, exptime, bias=None, dark_rate=None, flat=None,
               badpix=None, hotpix=None, saturation=SATURATION_ADU):
    """Detector-clean one raw detector image. Returns (data_e, err_e, qual).

    data_e is in electrons; err_e the 1-sigma error (photon + read noise);
    qual an int bitmask (QUAL_* bits). ron_e may be a scalar or a per-pixel
    array. Calibration arrays default to None (correction skipped).
    """
    adu = adu.astype(np.float32)
    qual = np.zeros(adu.shape, dtype=np.int32)
    qual[adu >= saturation] |= QUAL_SATURATED

    if bias is not None:
        adu = adu - bias.astype(np.float32)
    electrons = adu * np.float32(gain)

    # variance in electrons before dark subtraction (dark shot noise stays)
    var = np.maximum(electrons, 0.0) + np.float32(ron_e) ** 2

    if dark_rate is not None:
        electrons = electrons - dark_rate.astype(np.float32) * np.float32(exptime)
    if flat is not None:
        flat = np.where(flat == 0, np.float32(1.0), flat.astype(np.float32))
        electrons = electrons / flat
        var = var / flat ** 2
    if badpix is not None:
        qual[badpix != 0] |= QUAL_BADPIX
    if hotpix is not None:
        qual[hotpix != 0] |= QUAL_HOTPIX

    return electrons.astype(np.float32), np.sqrt(var).astype(np.float32), qual


def calib_map(frameset, tag):
    """band -> image array for the first frame of the given calibration tag."""
    frame = next((f for f in frameset if f.tag == tag), None)
    if frame is None:
        return {}
    out = {}
    with fits.open(frame.file) as hdul:
        for hdu in hdul[1:]:
            if hdu.is_image and hdu.data is not None:
                out[hdu.name] = np.asarray(hdu.data)
    return out


def _match(band_map, band, shape):
    """A calibration band array if it exists and matches the raw shape."""
    arr = band_map.get(band)
    return arr if arr is not None and arr.shape == shape else None


def clean_frame(path, calibs):
    """Clean every detector extension of one raw MEF. Returns band -> arrays."""
    result = {}
    with fits.open(path) as hdul:
        exptime = float(hdul[0].header.get("EXPTIME", 0.0))
        for hdu in hdul[1:]:
            if not hdu.is_image or hdu.data is None:
                continue
            band, adu = hdu.name, np.asarray(hdu.data)
            gain = float(hdu.header.get(GAIN_KEY, 1.0))
            res = _match(calibs["res"], band, adu.shape)
            ron_e = res.astype(np.float32) * gain if res is not None \
                else float(hdu.header.get(RON_KEY, 0.0))
            result[band] = clean_band(
                adu, gain, ron_e, exptime,
                bias=_match(calibs["bias"], band, adu.shape),
                dark_rate=_match(calibs["dark"], band, adu.shape),
                flat=_match(calibs["flat"], band, adu.shape),
                badpix=_match(calibs["badpix"], band, adu.shape),
                hotpix=_match(calibs["hotpix"], band, adu.shape))
    return result


def band_qc(data, qual):
    return {"ESO QC DETCAL MEAN": float(np.median(data)),
            "ESO QC DETCAL NBAD": int(np.count_nonzero(qual))}


def save_detcal_mef(catg, filename, bands, gains, primary_qc, frameset,
                    parameters, recipe_name, setup_header):
    """DFS primary via cpl.dfs, then DATA/ERR/QUAL extensions per detector."""
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
        for band, (data, err, qual) in bands.items():
            hdr = fits.Header()
            hdr["BUNIT"] = "e-"
            if gains.get(band) is not None:
                hdr[GAIN_KEY] = gains[band]
            for key, value in band_qc(data, qual).items():
                hdr[key] = value
            hdul.append(fits.ImageHDU(data, header=hdr, name=band))
            hdul.append(fits.ImageHDU(err, header=fits.Header({"BUNIT": "e-"}),
                                      name=f"{band}_ERR"))
            hdul.append(fits.ImageHDU(qual.astype(np.int32), name=f"{band}_QUAL"))
    return cpl.ui.Frame(filename, tag=catg, group=cpl.ui.Frame.FrameGroup.PRODUCT)


class AndesUtilDetcal(cpl.ui.PyRecipe):
    _name = "andes_util_detcal"
    _version = "0.1"
    _author = "ANDES DRS team"
    _email = "thomas.marquart@physics.uu.se"
    _copyright = "GPL-3.0-or-later"
    _synopsis = "Apply detector-signature corrections to raw frames"
    _description = (
        "Bias/dark/gain/flat/bad-pixel cleaning of each raw exposure, into "
        "electrons with an error map and quality mask. Products <base>_DETCAL "
        "(per exposure) and <base>_DETCAL_STACK (mean-combined).")

    def __init__(self):
        self.parameters = cpl.ui.ParameterList([
            cpl.ui.ParameterValue("andes_util_detcal.saturation",
                                  "Saturation threshold [ADU]",
                                  "andes_util_detcal", SATURATION_ADU),
        ])

    def run(self, frameset, settings):
        for name, value in settings.items():
            if name in [p.name for p in self.parameters]:
                self.parameters[name].value = value

        main = [f for f in frameset if f.tag not in DETCAL_CALIBS] or list(frameset)
        for frame in frameset:
            frame.group = (cpl.ui.Frame.FrameGroup.RAW if frame in main
                           else cpl.ui.Frame.FrameGroup.CALIB)
        base = base_tag([strip_suffix(f.tag) for f in main])
        calibs = {"bias": calib_map(frameset, "MASTER_BIAS"),
                  "res": calib_map(frameset, "MASTER_BIAS_RES"),
                  "dark": calib_map(frameset, "MASTER_DARK"),
                  "flat": calib_map(frameset, "DETFLAT"),
                  "badpix": calib_map(frameset, "BAD_PIXEL_MASK"),
                  "hotpix": calib_map(frameset, "HOT_PIXEL_MASK")}

        setup_header = fits.getheader(main[0].file)
        with fits.open(main[0].file) as hdul:
            gains = {h.name: h.header.get(GAIN_KEY) for h in hdul[1:] if h.is_image}

        products = cpl.ui.FrameSet()
        stack_sum, stack_var, stack_qual = {}, {}, {}
        for i, frame in enumerate(main):
            bands = clean_frame(frame.file, calibs)
            products.append(save_detcal_mef(
                f"{base}_DETCAL", f"{base.lower()}_detcal_{i:03d}.fits", bands,
                gains, {}, frameset, self.parameters, self._name,
                fits.getheader(frame.file)))
            for band, (data, err, qual) in bands.items():
                stack_sum[band] = stack_sum.get(band, 0) + data
                stack_var[band] = stack_var.get(band, 0) + err.astype(np.float64) ** 2
                stack_qual[band] = stack_qual.get(band, 0) | qual

        n = len(main)
        stack = {band: (stack_sum[band] / n,
                        (np.sqrt(stack_var[band]) / n).astype(np.float32),
                        stack_qual[band]) for band in stack_sum}
        products.append(save_detcal_mef(
            f"{base}_DETCAL_STACK", f"{base.lower()}_detcal_stack.fits", stack,
            gains, {"ESO QC DETCAL NFRAMES": n}, frameset, self.parameters,
            self._name, setup_header))
        return products
