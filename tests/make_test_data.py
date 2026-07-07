"""Generate a synthetic night of ANDES raw data for exercising the workflow.

Usage: uv run python tests/make_test_data.py <output_dir>

Covers three instrument setups: RIZ SL-UNI (VIS, with bias), YJH SL-UNI
(NIR, no bias) and YJH IFU-AO, plus the static calibration tables.
Grammar: Templates Manual v2.0 (two slots A,B; calibration fibre C in
ins.calfib). Real-pixel raw frames come from the E2E simulator instead
(andes-sim make-raw / night); this header-only generator stays for fast CI.
"""

import itertools
import sys
from pathlib import Path

from astropy.io import fits

counter = itertools.count(1)


def long_key(key):
    return "HIERARCH ESO " + key.upper().replace(".", " ") if "." in key else key.upper()


def write_frame(outdir, arm, mjd, keywords):
    hdu = fits.PrimaryHDU()
    hdu.header["INSTRUME"] = "ANDES"
    hdu.header["MJD-OBS"] = mjd
    hdu.header[long_key("seq.arm")] = arm
    for key, value in keywords.items():
        hdu.header[long_key(key)] = value
    name = f"ANDES_{arm}_{next(counter):04d}.fits"
    hdu.writeto(Path(outdir) / name, overwrite=True)


def calib(dpr_type, tech, tpl, catg="CALIB", **extra):
    return {"dpr.catg": catg, "dpr.type": dpr_type, "dpr.tech": tech,
            "tpl.start": tpl, "det.binx": 1, "det.biny": 1, **extra}


def sl(dpr_type, tpl, tech="ECHELLE,FIBER", calfib="OFF", **extra):
    return calib(dpr_type, tech, tpl,
                 **{"ins.mode": "SL-UNI", "ins.calfib": calfib, **extra})


def ifu(dpr_type, tpl, tech="ECHELLE,IFU", calfib="OFF", **extra):
    return calib(dpr_type, tech, tpl,
                 **{"ins.mode": "IFU-AO", "ins.calfib": calfib, **extra})


def make_setup(outdir, arm, mode, mjd0, with_bias):
    frames = []
    if with_bias:
        frames += [calib("BIAS", "IMAGE", f"{arm}-bias")] * 5
    frames += [calib("DARK", "IMAGE", f"{arm}-dark")] * 3
    frames += [calib("FLAT,LAMP", "IMAGE", f"{arm}-led", catg="TECHNICAL")] * 4

    if mode == "SL-UNI":
        frames += [sl("ORDERDEF,LAMP,OFF", f"{arm}-ord"),
                   sl("ORDERDEF,OFF,LAMP", f"{arm}-ord"),
                   sl("SLITMASK,FP,OFF", f"{arm}-slit", calfib="FP"),
                   sl("SLITMASK,OFF,FP", f"{arm}-slit", calfib="FP"),
                   sl("FLAT,LAMP,OFF", f"{arm}-flat"),
                   sl("FLAT,OFF,LAMP", f"{arm}-flat"),
                   sl("WAVE,HCL,FP", f"{arm}-wave", calfib="OFF"),
                   sl("WAVE,FP,HCL", f"{arm}-wave", calfib="OFF"),
                   sl("WAVE,FP,FP", f"{arm}-wave", calfib="FP"),
                   sl("WAVE,LFC,FP", f"{arm}-lfc", calfib="FP"),
                   sl("WAVE,FP,LFC", f"{arm}-lfc", calfib="FP"),
                   sl("FLAT,SKY,SKY", f"{arm}-eff"),
                   sl("FLAT,SKY,SKY", f"{arm}-eff"),
                   sl("STD,FLUX,SKY", f"{arm}-flux"),
                   sl("STD,TELLURIC,SKY", f"{arm}-tell"),
                   sl("STD,RV,SKY", f"{arm}-rv", calfib="FP"),
                   sl("OBJECT,SKY", f"{arm}-sci", calfib="FP", catg="SCIENCE"),
                   sl("OBJECT,WAVE", f"{arm}-tc", calfib="FP", catg="SCIENCE"),
                   # ABBA swapping sequence in one template
                   sl("OBJECT,SKY", f"{arm}-swap", "ECHELLE,FIBER,SWAPPING",
                      calfib="FP", catg="SCIENCE"),
                   sl("SKY,OBJECT", f"{arm}-swap", "ECHELLE,FIBER,SWAPPING",
                      calfib="FP", catg="SCIENCE"),
                   sl("SKY,OBJECT", f"{arm}-swap", "ECHELLE,FIBER,SWAPPING",
                      calfib="FP", catg="SCIENCE"),
                   sl("OBJECT,SKY", f"{arm}-swap", "ECHELLE,FIBER,SWAPPING",
                      calfib="FP", catg="SCIENCE")]
    else:
        frames += [ifu("ORDERDEF,LAMP", f"{arm}-ifu-ord"),
                   ifu("SLITMASK,FP", f"{arm}-ifu-slit", calfib="FP"),
                   ifu("FLAT,LAMP", f"{arm}-ifu-flat"),
                   ifu("WAVE,HCL", f"{arm}-ifu-wave", calfib="FP"),
                   ifu("WAVE,FP", f"{arm}-ifu-wave", calfib="FP"),
                   ifu("FLAT,SKY", f"{arm}-ifu-eff"),
                   ifu("STD,FLUX", f"{arm}-ifu-flux"),
                   ifu("STD,TELLURIC", f"{arm}-ifu-tell"),
                   ifu("STD,RV", f"{arm}-ifu-rv", calfib="FP"),
                   ifu("OBJECT", f"{arm}-ifu-sci", catg="SCIENCE"),
                   ifu("SKY", f"{arm}-ifu-sci", catg="SCIENCE")]

    for i, keywords in enumerate(frames):
        write_frame(outdir, arm, mjd0 + i * 0.001, keywords)


def make_static_tables(outdir, arm, mjd):
    for catg in ("HCL_LINES_TABLE", "STD_STAR_TABLE", "STD_TELL_TABLE"):
        write_frame(outdir, arm, mjd, {"pro.catg": catg})


def main(outdir):
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    make_setup(outdir, "RIZ", "SL-UNI", 61000.0, with_bias=True)
    make_setup(outdir, "YJH", "SL-UNI", 61000.0, with_bias=False)
    make_setup(outdir, "YJH", "IFU-AO", 61000.2, with_bias=False)
    for arm in ("RIZ", "YJH"):
        make_static_tables(outdir, arm, 61000.0)
    print(f"wrote {next(counter) - 1} files to {outdir}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "test_data")
