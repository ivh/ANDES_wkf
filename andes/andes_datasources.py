"""Data sources: how raw frames and static tables are grouped and associated.

All data sources are spectrograph- and mode-generic: grouping and matching
run over the setup keywords (arm, binning, observing mode), so the same
task graph serves UBV, RIZ, YJH and K in both SL-UNI and IFU-AO.
"""

from edps import data_source

from . import andes_keywords as kwd
from . import andes_classification as cls


def raw_source(name, rules, setup):
    builder = data_source(name)
    for rule in rules:
        builder.with_classification_rule(rule)
    # one job per template execution and instrument setup
    return (builder
            .with_grouping_keywords(setup + [kwd.tpl_start])
            .with_setup_keywords(setup)
            .with_match_keywords(setup)
            .build())


bias = raw_source("BIAS", [cls.bias_class], kwd.det_setup)
dark = raw_source("DARK", [cls.dark_class], kwd.det_setup)
ledff = raw_source("LEDFF", [cls.ledff_class], kwd.det_setup)

# per-slit frames of one template execution form a single group, whether the
# template exposes slits separately (A/C/B), together (ACB) or as IFU
orderdef = raw_source("ORDERDEF", [cls.orderdef_a_class, cls.orderdef_c_class,
                                   cls.orderdef_b_class, cls.orderdef_acb_class,
                                   cls.orderdef_ifu_class], kwd.inst_setup)

slit = raw_source("SLIT", [cls.slit_class, cls.slit_ifu_class], kwd.inst_setup)
lsf = raw_source("LSF", [cls.lsf_class, cls.lsf_ifu_class], kwd.inst_setup)

flat = raw_source("FLAT", [cls.flat_a_class, cls.flat_c_class, cls.flat_b_class,
                           cls.flat_acb_class, cls.flat_ifu_class], kwd.inst_setup)

wave_fp = raw_source("WAVE_FP", [cls.wave_hcl_a_class, cls.wave_hcl_b_class,
                                 cls.wave_fp_class, cls.wave_hcl_ifu_class], kwd.inst_setup)
wave_lfc = raw_source("WAVE_LFC", [cls.wave_lfc_class, cls.wave_lfc_ifu_class], kwd.inst_setup)

eff = raw_source("EFF", [cls.eff_class, cls.eff_ifu_class], kwd.inst_setup)
std_flux = raw_source("STD_FLUX", [cls.std_flux_class, cls.std_flux_ifu_class], kwd.inst_setup)
std_telluric = raw_source("STD_TELLURIC", [cls.std_telluric_class,
                                           cls.std_telluric_ifu_class], kwd.inst_setup)
std_rv = raw_source("STD_RV", [cls.std_rv_class], kwd.inst_setup)

science = raw_source("SCIENCE", [cls.science_sl_class, cls.science_ifu_class], kwd.inst_setup)


def static_table(rule):
    # one file per spectrograph, matched on instrument and arm only
    return (data_source(rule.classification)
            .with_classification_rule(rule)
            .with_grouping_keywords([kwd.pro_catg])
            .with_match_keywords([kwd.instrume, kwd.seq_arm])
            .build())


hcl_lines = static_table(cls.hcl_lines_class)
std_star_table = static_table(cls.std_star_table_class)
std_tell_table = static_table(cls.std_tell_table_class)
