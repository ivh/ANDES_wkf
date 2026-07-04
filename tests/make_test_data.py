"""Generate a synthetic night of ANDES raw data for exercising the workflow.

Usage: uv run python tests/make_test_data.py <output_dir>

Covers three instrument setups: RIZ SL-UNI (VIS, with bias), YJH SL-UNI
(NIR, no bias) and YJH IFU-AO, plus the static calibration tables.
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


def sl(dpr_type, tpl, tech="ECHELLE,FIBER", **extra):
    return calib(dpr_type, tech, tpl, **{"ins.mode": "SL-UNI", **extra})


def ifu(dpr_type, tpl, tech="ECHELLE,IFU", **extra):
    return calib(dpr_type, tech, tpl, **{"ins.mode": "IFU-AO", **extra})


def make_setup(outdir, arm, mode, mjd0, with_bias):
    frames = []
    if with_bias:
        frames += [calib("BIAS", "IMAGE", f"{arm}-bias")] * 5
    frames += [calib("DARK", "IMAGE", f"{arm}-dark")] * 3
    frames += [calib("FLAT,LAMP", "IMAGE", f"{arm}-led", catg="TECHNICAL")] * 4

    if mode == "SL-UNI":
        frames += [sl("ORDERDEF,LAMP,OFF,OFF", f"{arm}-ord"),
                   sl("ORDERDEF,OFF,LAMP,OFF", f"{arm}-ord"),
                   sl("ORDERDEF,OFF,OFF,LAMP", f"{arm}-ord"),
                   sl("SLIT,FP,FP,FP", f"{arm}-slit"),
                   sl("LSF,FP,FP,FP", f"{arm}-lsf"),
                   sl("FLAT,LAMP,OFF,OFF", f"{arm}-flat"),
                   sl("FLAT,OFF,LAMP,OFF", f"{arm}-flat"),
                   sl("FLAT,OFF,OFF,LAMP", f"{arm}-flat"),
                   sl("WAVE,HCL,FP,FP", f"{arm}-wave"),
                   sl("WAVE,FP,FP,HCL", f"{arm}-wave"),
                   sl("WAVE,FP,FP,FP", f"{arm}-wave"),
                   sl("WAVE,LFC,FP,LFC", f"{arm}-lfc"),
                   sl("EFF,SKY,OFF,SKY", f"{arm}-eff"),
                   sl("EFF,SKY,OFF,SKY", f"{arm}-eff"),
                   sl("STD,FLUX,OFF,SKY", f"{arm}-flux"),
                   sl("STD,TELLURIC,OFF,SKY", f"{arm}-tell"),
                   sl("STD,RV,FP,SKY", f"{arm}-rv"),
                   sl("OBJECT,FP,SKY", f"{arm}-sci", catg="SCIENCE"),
                   # ABBA swapping sequence in one template
                   sl("OBJECT,FP,SKY", f"{arm}-swap", "ECHELLE,FIBER,SWAPPING", catg="SCIENCE"),
                   sl("SKY,FP,OBJECT", f"{arm}-swap", "ECHELLE,FIBER,SWAPPING", catg="SCIENCE"),
                   sl("SKY,FP,OBJECT", f"{arm}-swap", "ECHELLE,FIBER,SWAPPING", catg="SCIENCE"),
                   sl("OBJECT,FP,SKY", f"{arm}-swap", "ECHELLE,FIBER,SWAPPING", catg="SCIENCE")]
    else:
        frames += [ifu("ORDERDEF,LAMP", f"{arm}-ifu-ord"),
                   ifu("SLIT,FP", f"{arm}-ifu-slit"),
                   ifu("LSF,FP", f"{arm}-ifu-lsf"),
                   ifu("FLAT,LAMP", f"{arm}-ifu-flat"),
                   ifu("WAVE,HCL,FP", f"{arm}-ifu-wave"),
                   ifu("EFF,SKY", f"{arm}-ifu-eff"),
                   ifu("STD,FLUX", f"{arm}-ifu-flux"),
                   ifu("STD,TELLURIC", f"{arm}-ifu-tell"),
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
