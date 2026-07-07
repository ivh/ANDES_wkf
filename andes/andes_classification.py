"""Classification rules for ANDES raw frames, static tables and products.

Naming conventions (Templates Manual E-AND-SW-MAN-06-00-001 v2.0, Tables
2 and 5; see calibration_plan.yaml reconciliation item 10):
- 1:1 correspondence between raw DPR.TYPE kinds, templates and recipes
- DPR.TYPE carries two sub-slit values: first fiber A, second fiber B;
  the calibration fibre C is NOT in DPR.TYPE (ESO-044156) but in the
  dedicated keyword ins.calfib, see andes_rules for the grammar
- product PRO.CATG values carry per-slit suffixes _A, _B, _C or _IFU
"""

from edps import classification_rule

from . import andes_keywords as kwd
from .andes_rules import is_science_sl, is_science_ifu, is_slitmask_sl

andes = {kwd.instrume: "ANDES"}
calib = {**andes, kwd.dpr_catg: "CALIB"}
tech_image = {kwd.dpr_tech: "IMAGE"}
tech_sl = {kwd.dpr_tech: "ECHELLE,FIBER"}
tech_ifu = {kwd.dpr_tech: "ECHELLE,IFU"}


def calib_rule(tag, dpr_type, tech):
    return classification_rule(tag, {**calib, kwd.dpr_type: dpr_type, **tech})


# --- detector calibrations (per detector, observing-mode independent) ---

bias_class = calib_rule("BIAS", "BIAS", tech_image)
dark_class = calib_rule("DARK", "DARK", tech_image)
# LED flats are DPR.CATG=TECHNICAL per Table 2 (deferred to AD4)
ledff_class = classification_rule("LEDFF", {**andes, kwd.dpr_catg: "TECHNICAL",
                                            kwd.dpr_type: "FLAT,LAMP", **tech_image})

# --- echelle calibrations, SL-UNI ---

orderdef_a_class = calib_rule("ORDERDEF_A", "ORDERDEF,LAMP,OFF", tech_sl)
orderdef_b_class = calib_rule("ORDERDEF_B", "ORDERDEF,OFF,LAMP", tech_sl)

# manual Table 5 allows CALIB or TECHNICAL for slit-mask frames
slitmask_class = classification_rule("SLITMASK", is_slitmask_sl)

flat_a_class = calib_rule("FLAT_A", "FLAT,LAMP,OFF", tech_sl)
flat_b_class = calib_rule("FLAT_B", "FLAT,OFF,LAMP", tech_sl)

wave_hcl_a_class = calib_rule("WAVE_HCL_A", "WAVE,HCL,FP", tech_sl)
wave_hcl_b_class = calib_rule("WAVE_HCL_B", "WAVE,FP,HCL", tech_sl)
wave_fp_class = calib_rule("WAVE_FP", "WAVE,FP,FP", tech_sl)
wave_lfc_a_class = calib_rule("WAVE_LFC_A", "WAVE,LFC,FP", tech_sl)
wave_lfc_b_class = calib_rule("WAVE_LFC_B", "WAVE,FP,LFC", tech_sl)

eff_class = calib_rule("EFF", "FLAT,SKY,SKY", tech_sl)
std_flux_class = calib_rule("STD_FLUX", ["STD,FLUX,SKY", "STD,SKY,FLUX"], tech_sl)
std_telluric_class = calib_rule("STD_TELLURIC",
                                ["STD,TELLURIC,SKY", "STD,SKY,TELLURIC"], tech_sl)
std_rv_class = calib_rule("STD_RV", ["STD,RV,SKY", "STD,SKY,RV"], tech_sl)

# --- echelle calibrations, IFU-AO ---
# The manual defines no IFU slit-mask template; SLITMASK,FP kept as our
# proposed type so the IFU cascade stays organizable (reconciliation 3).

orderdef_ifu_class = calib_rule("ORDERDEF_IFU", "ORDERDEF,LAMP", tech_ifu)
slitmask_ifu_class = calib_rule("SLITMASK_IFU", ["SLITMASK,FP", "SLITMASK,LFC"], tech_ifu)
flat_ifu_class = calib_rule("FLAT_IFU", "FLAT,LAMP", tech_ifu)
wave_hcl_ifu_class = calib_rule("WAVE_HCL_IFU", "WAVE,HCL", tech_ifu)
wave_fp_ifu_class = calib_rule("WAVE_FP_IFU", "WAVE,FP", tech_ifu)
wave_lfc_ifu_class = calib_rule("WAVE_LFC_IFU", "WAVE,LFC", tech_ifu)
eff_ifu_class = calib_rule("EFF_IFU", "FLAT,SKY", tech_ifu)
std_flux_ifu_class = calib_rule("STD_FLUX_IFU", "STD,FLUX", tech_ifu)
std_telluric_ifu_class = calib_rule("STD_TELLURIC_IFU", "STD,TELLURIC", tech_ifu)
std_rv_ifu_class = calib_rule("STD_RV_IFU", "STD,RV", tech_ifu)

# --- science ---

science_sl_class = classification_rule("SCIENCE", is_science_sl)
science_ifu_class = classification_rule("SCIENCE_IFU", is_science_ifu)

# --- static tables (classified by PRO.CATG) ---

hcl_lines_class = classification_rule("HCL_LINES_TABLE")
std_star_table_class = classification_rule("STD_STAR_TABLE")
std_tell_table_class = classification_rule("STD_TELL_TABLE")

# --- products exchanged between tasks (PRO.CATG) ---

SLIT_TAGS = ["A", "B", "C", "IFU"]


def per_slit(prefix):
    return [classification_rule(f"{prefix}_{s}") for s in SLIT_TAGS]


master_bias_class = classification_rule("MASTER_BIAS")
master_bias_res_class = classification_rule("MASTER_BIAS_RES")
master_dark_class = classification_rule("MASTER_DARK")
hot_pixel_mask_class = classification_rule("HOT_PIXEL_MASK")
bad_pixel_mask_class = classification_rule("BAD_PIXEL_MASK")
detflat_class = classification_rule("DETFLAT")
detlin_class = classification_rule("DETLIN")

order_table_classes = per_slit("ORDER_TABLE")
slit_curve_classes = per_slit("SLIT_CURVE")
lsf_model_classes = per_slit("LSF_MODEL")

order_profile_classes = per_slit("ORDER_PROFILE")
master_flat_classes = per_slit("MASTER_FLAT")
blaze_classes = per_slit("BLAZE")

wave_table_classes = per_slit("WAVE_TABLE")
wave_matrix_classes = per_slit("WAVE_MATRIX")
dll_matrix_classes = per_slit("DLL_MATRIX")
s1d_wave_classes = per_slit("S1D_WAVE")
wave_map_class = classification_rule("WAVE_MAP")

rel_eff_classes = per_slit("REL_EFF")
abs_eff_classes = per_slit("ABS_EFF")
tell_model_class = classification_rule("TELL_MODEL")

# full set of wavelength-calibration products needed downstream
wave_product_classes = (wave_table_classes + wave_matrix_classes + dll_matrix_classes
                        + s1d_wave_classes + [wave_map_class])
