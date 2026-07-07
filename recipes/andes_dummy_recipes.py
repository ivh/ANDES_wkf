"""Dummy pyesorex recipes for exercising the ANDES EDPS workflow end-to-end.

Every recipe writes minimal FITS images whose PRO.CATG values follow the
resolved product naming scheme, inheriting the instrument setup keywords
from the first input frame so that EDPS can classify and associate the
products. No data processing happens here; replace recipe by recipe with
real implementations.
"""

import os

import cpl
from astropy.io import fits

PIPE_ID = "andes/0.1"

# keywords forwarded explicitly so products always match on the setup
SETUP_KEYS = ["INSTRUME", "MJD-OBS", "HIERARCH ESO SEQ ARM", "HIERARCH ESO INS MODE",
              "HIERARCH ESO DET BINX", "HIERARCH ESO DET BINY", "HIERARCH ESO TPL START"]

# products associated into detcal jobs (anything else in the SOF is the main group)
DETCAL_CALIBS = {"MASTER_BIAS", "MASTER_BIAS_RES", "MASTER_DARK", "HOT_PIXEL_MASK",
                 "BAD_PIXEL_MASK", "DETFLAT", "DETLIN"}

MAIN_SUFFIXES = ("_DETCAL_STACK", "_DETCAL", "_BKGR_SUB")


def strip_suffix(tag):
    for suffix in MAIN_SUFFIXES:
        if tag.endswith(suffix):
            return tag[: -len(suffix)]
    return tag


def base_tag(tags):
    prefix = os.path.commonprefix(sorted(set(tags)))
    return prefix.rstrip("_,") or "UNKNOWN"


def main_frames(frameset, recipe_name):
    if recipe_name == "andes_util_detcal":
        selected = [f for f in frameset if f.tag not in DETCAL_CALIBS]
    else:
        selected = [f for f in frameset if f.tag.endswith(MAIN_SUFFIXES)]
    return selected or list(frameset)


def slits_of(frame):
    header = fits.getheader(frame.file)
    mode = header.get("HIERARCH ESO INS MODE", "")
    return ["IFU"] if mode == "IFU-AO" else ["A", "B", "C"]


def sci_slits(slits):
    # products of two-aperture recipes exist for the science slits only
    return slits if slits == ["IFU"] else ["A", "B"]


def slitwise(*prefixes, extra=(), slit_selector=lambda slits: slits):
    def build(base, slits):
        chosen = slit_selector(slits)
        return [f"{p}_{s}" for p in prefixes for s in chosen] + list(extra)
    return build


def fixed(*catgs):
    return lambda base, slits: list(catgs)


def util_detcal(base, slits):
    return [f"{base}_DETCAL", f"{base}_DETCAL_STACK"]


def util_bkgr(base, slits):
    return [f"{base}_BKGR_SUB"]


def util_extract(base, slits):
    return ([f"{base}_EXTRACT_S1D_{s}" for s in slits]
            + [f"{base}_EXTRACT_SLIT_ILLUM_{s}" for s in slits]
            + [f"{base}_EXTRACT_2DMODEL"])


RECIPES = {
    "andes_util_detcal": util_detcal,
    "andes_util_bkgr": util_bkgr,
    "andes_util_extract": util_extract,
    # andes_cal_bias has a real implementation (andes_cal_bias.py)
    "andes_cal_dark": fixed("MASTER_DARK", "HOT_PIXEL_MASK"),
    "andes_cal_led": fixed("BAD_PIXEL_MASK", "DETFLAT", "DETLIN"),
    "andes_cal_orderdef": slitwise("ORDER_TABLE"),
    "andes_cal_slit": slitwise("SLIT_CURVE", "LINE_TABLE_RAW"),
    "andes_cal_LSF": slitwise("LSF_MODEL", "LINE_TABLE_RAW"),
    "andes_cal_flat": slitwise("ORDER_PROFILE", "MASTER_FLAT", "BLAZE"),
    "andes_cal_wave_FP": slitwise("LINE_TABLE_FP", "LINE_TABLE_HCL", "LINE_TABLE_RAW",
                                  "WAVE_TABLE", "WAVE_MATRIX", "DLL_MATRIX", "S1D_WAVE",
                                  extra=("WAVE_MAP",)),
    "andes_cal_wave_LFC": slitwise("LINE_TABLE_LFC", "LINE_TABLE_RAW",
                                   "WAVE_TABLE", "WAVE_MATRIX", "DLL_MATRIX", "S1D_WAVE",
                                   extra=("WAVE_MAP",)),
    "andes_cal_rel_eff": slitwise("REL_EFF", slit_selector=sci_slits),
    "andes_cal_flux": slitwise("S1D_STD_FLUX", "SS1D_STD_FLUX", "ABS_EFF",
                               slit_selector=sci_slits),
    "andes_cal_telluric_std": slitwise("S1D_STD_TELL", "SS1D_STD_TELL",
                                       extra=("TELL_MODEL",), slit_selector=sci_slits),
    "andes_science": slitwise("S1D", "SS1D", "S1D_SKYSUB", "SS1D_FINAL",
                              "WAVE_MATRIX_DRIFT",
                              extra=("BACKGROUND_MAP",), slit_selector=sci_slits),
}


def run_dummy(recipe, frameset):
    main = main_frames(frameset, recipe.name)
    base = base_tag([strip_suffix(f.tag) for f in main])
    slits = slits_of(main[0])

    # cpl_dfs_save_image needs the frameset classified into RAW/CALIB
    main_tags = {f.tag for f in main}
    for frame in frameset:
        frame.group = (cpl.ui.Frame.FrameGroup.RAW if frame.tag in main_tags
                       else cpl.ui.Frame.FrameGroup.CALIB)

    header = fits.getheader(main[0].file)
    products = cpl.ui.FrameSet()
    for catg in RECIPES[recipe.name](base, slits):
        applist = cpl.core.PropertyList()
        applist.append(cpl.core.Property("ESO PRO CATG", catg))
        for key in SETUP_KEYS:
            if key in header:
                applist.append(cpl.core.Property(key, header[key]))
        filename = f"{catg.lower()}.fits"
        image = cpl.core.Image.zeros(2, 2, cpl.core.Type.FLOAT)
        cpl.dfs.save_image(frameset, recipe.parameters, frameset, image,
                           recipe.name, applist, PIPE_ID, filename, inherit=main[0])
        products.append(cpl.ui.Frame(filename, tag=catg,
                                     group=cpl.ui.Frame.FrameGroup.PRODUCT))
    return products


def make_recipe(recipe_name):
    class_name = "".join(part.capitalize() for part in recipe_name.split("_"))

    def __init__(self):
        self.parameters = cpl.ui.ParameterList([])

    def run(self, frameset, settings):
        return run_dummy(self, frameset)

    return type(class_name, (cpl.ui.PyRecipe,), {
        "_name": recipe_name,
        "_version": "0.1",
        "_author": "ANDES DRS team",
        "_email": "thomas.marquart@physics.uu.se",
        "_copyright": "GPL-3.0-or-later",
        "_synopsis": f"Dummy {recipe_name}",
        "_description": f"Dummy stand-in for {recipe_name}, writes empty products.",
        "__init__": __init__,
        "run": run,
    })


for _name in RECIPES:
    _cls = make_recipe(_name)
    globals()[_cls.__name__] = _cls
