"""Complex classification functions (rules that cannot be keyword-value dicts).

DPR.TYPE grammar (Templates Manual E-AND-SW-MAN-06-00-001 v2.0):
- echelle calibrations: "<KIND>,<A>,<B>" where A and B are the two SL
  pseudo-slits; IFU frames use "<KIND>,<slit>". The calibration fibre C
  is not part of DPR.TYPE (ESO-044156); its source is in ins.calfib.
- science frames carry no KIND prefix: "<A>,<B>" (SL) or plain
  "OBJECT"/"SKY" (IFU); DPR.CATG=SCIENCE identifies them. The second
  slot may be WAVE (TC mode: simultaneous wavelength reference in the
  other fiber).
- DPR.TECH may carry a third element (SWAPPING/OFFSET/DITHERING), hence
  the prefix matching below
"""

from . import andes_keywords as kwd

SLIT_SOURCES = {"OBJECT", "SKY"}
SCIENCE_SOURCES = SLIT_SOURCES | {"WAVE"}


def _is_science(f, tech_prefix):
    return (f[kwd.instrume] == "ANDES"
            and f[kwd.dpr_catg] == "SCIENCE"
            and (f[kwd.dpr_tech] or "").startswith(tech_prefix))


def is_science_sl(f):
    parts = (f[kwd.dpr_type] or "").split(",")
    return (_is_science(f, "ECHELLE,FIBER")
            and len(parts) == 2
            and all(p in SCIENCE_SOURCES for p in parts)
            and any(p in SLIT_SOURCES for p in parts))


def is_science_ifu(f):
    return (_is_science(f, "ECHELLE,IFU")
            and f[kwd.dpr_type] in ("OBJECT", "SKY"))


def is_slitmask_sl(f):
    # manual Table 5 allows CALIB or TECHNICAL for slit-mask frames
    return (f[kwd.instrume] == "ANDES"
            and f[kwd.dpr_catg] in ("CALIB", "TECHNICAL")
            and f[kwd.dpr_type] in ("SLITMASK,FP,OFF", "SLITMASK,OFF,FP")
            and f[kwd.dpr_tech] == "ECHELLE,FIBER")
