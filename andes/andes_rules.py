"""Complex classification functions (rules that cannot be keyword-value dicts).

DPR.TYPE grammar (resolved from E-AND-SW-SPE-09-00-002 v1.2):
- echelle calibrations: "<KIND>,<A>,<C>,<B>" where A and B are the two SL
  pseudo-slits and C the calibration fibre between them; IFU frames use
  "<KIND>,<slit>[,<calib>]"
- science frames carry no KIND prefix: "<A>,<C>,<B>" (SL) or plain
  "OBJECT"/"SKY" (IFU); DPR.CATG=SCIENCE identifies them
- DPR.TECH may carry a third element (SWAPPING/OFFSET/DITHERING), hence
  the prefix matching below
"""

from . import andes_keywords as kwd

SLIT_SOURCES = {"OBJECT", "SKY"}
SIMCAL_SOURCES = {"FP", "LFC", "DARK"}


def _is_science(f, tech_prefix):
    return (f[kwd.instrume] == "ANDES"
            and f[kwd.dpr_catg] == "SCIENCE"
            and (f[kwd.dpr_tech] or "").startswith(tech_prefix))


def is_science_sl(f):
    parts = (f[kwd.dpr_type] or "").split(",")
    return (_is_science(f, "ECHELLE,FIBER")
            and len(parts) == 3
            and parts[0] in SLIT_SOURCES
            and parts[1] in SIMCAL_SOURCES
            and parts[2] in SLIT_SOURCES)


def is_science_ifu(f):
    return (_is_science(f, "ECHELLE,IFU")
            and f[kwd.dpr_type] in ("OBJECT", "SKY"))
