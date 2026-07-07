"""Classification rules: every raw type matches exactly its intended tag."""

import pytest

from andes import andes_classification as cls
from andes import andes_keywords as kwd
from edps.generator.classif_rule import BaseClassificationRule


class FakeFile(dict):
    """Minimal stand-in for edps FitsFile: context manager, None for missing keys."""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def __getitem__(self, key):
        return self.get(key)


def raw_rules():
    rules = [v for v in vars(cls).values()
             if isinstance(v, BaseClassificationRule) and not v.is_product()]
    assert rules
    return rules


def header(catg, dpr_type, tech):
    return FakeFile({kwd.instrume: "ANDES", kwd.dpr_catg: catg,
                     kwd.dpr_type: dpr_type, kwd.dpr_tech: tech})


SL = "ECHELLE,FIBER"
IFU = "ECHELLE,IFU"

# one sample header per expected tag (grammar: Templates Manual v2.0,
# two slots A,B; calibration fibre C in ins.calfib, not classified on)
SAMPLES = {
    "BIAS": header("CALIB", "BIAS", "IMAGE"),
    "DARK": header("CALIB", "DARK", "IMAGE"),
    "LEDFF": header("TECHNICAL", "FLAT,LAMP", "IMAGE"),
    "ORDERDEF_A": header("CALIB", "ORDERDEF,LAMP,OFF", SL),
    "ORDERDEF_B": header("CALIB", "ORDERDEF,OFF,LAMP", SL),
    "ORDERDEF_IFU": header("CALIB", "ORDERDEF,LAMP", IFU),
    "SLITMASK": header("CALIB", "SLITMASK,FP,OFF", SL),
    "SLITMASK_IFU": header("CALIB", "SLITMASK,FP", IFU),
    "FLAT_A": header("CALIB", "FLAT,LAMP,OFF", SL),
    "FLAT_B": header("CALIB", "FLAT,OFF,LAMP", SL),
    "FLAT_IFU": header("CALIB", "FLAT,LAMP", IFU),
    "WAVE_HCL_A": header("CALIB", "WAVE,HCL,FP", SL),
    "WAVE_HCL_B": header("CALIB", "WAVE,FP,HCL", SL),
    "WAVE_FP": header("CALIB", "WAVE,FP,FP", SL),
    "WAVE_LFC_A": header("CALIB", "WAVE,LFC,FP", SL),
    "WAVE_LFC_B": header("CALIB", "WAVE,FP,LFC", SL),
    "WAVE_HCL_IFU": header("CALIB", "WAVE,HCL", IFU),
    "WAVE_FP_IFU": header("CALIB", "WAVE,FP", IFU),
    "WAVE_LFC_IFU": header("CALIB", "WAVE,LFC", IFU),
    "EFF": header("CALIB", "FLAT,SKY,SKY", SL),
    "EFF_IFU": header("CALIB", "FLAT,SKY", IFU),
    "STD_FLUX": header("CALIB", "STD,FLUX,SKY", SL),
    "STD_FLUX_IFU": header("CALIB", "STD,FLUX", IFU),
    "STD_TELLURIC": header("CALIB", "STD,SKY,TELLURIC", SL),
    "STD_TELLURIC_IFU": header("CALIB", "STD,TELLURIC", IFU),
    "STD_RV": header("CALIB", "STD,RV,SKY", SL),
    "STD_RV_IFU": header("CALIB", "STD,RV", IFU),
    "SCIENCE": header("SCIENCE", "OBJECT,SKY", SL),
    "SCIENCE_IFU": header("SCIENCE", "OBJECT", IFU),
}


@pytest.mark.parametrize("tag", SAMPLES)
def test_sample_classifies_as_exactly_its_tag(tag):
    matches = {r.classification for r in raw_rules() if r.is_classified(SAMPLES[tag])}
    assert matches == {tag}


def test_slitmask_technical_variant():
    assert cls.slitmask_class.is_classified(header("TECHNICAL", "SLITMASK,OFF,FP", SL))


@pytest.mark.parametrize("dpr_type,tech", [
    ("OBJECT,SKY", SL),
    ("SKY,OBJECT", SL),                         # swapped counterpart
    ("OBJECT,SKY", SL + ",SWAPPING"),
    ("OBJECT,WAVE", SL),                        # TC: simultaneous reference
    ("WAVE,OBJECT", SL),
    ("OBJECT,WAVE", SL + ",OFFSET"),
    ("SKY,SKY", SL),                            # sky-only offset exposure
])
def test_science_sl_variants(dpr_type, tech):
    assert cls.science_sl_class.is_classified(header("SCIENCE", dpr_type, tech))


@pytest.mark.parametrize("dpr_type,tech", [
    ("OBJECT", IFU),
    ("SKY", IFU),
    ("OBJECT", IFU + ",DITHERING"),
])
def test_science_ifu_variants(dpr_type, tech):
    assert cls.science_ifu_class.is_classified(header("SCIENCE", dpr_type, tech))


@pytest.mark.parametrize("f", [
    header("CALIB", "OBJECT,SKY", SL),              # wrong category
    header("SCIENCE", "OBJECT,FP,SKY", SL),         # old three-slot grammar
    header("SCIENCE", "OBJECT,FLAT", SL),           # invalid slit source
    header("SCIENCE", "WAVE,WAVE", SL),             # no on-sky slot
    header("SCIENCE", "OBJECT,SKY", IFU),           # SL pattern with IFU tech
    header("CALIB", "WAVE,HCL,FP,FP", SL),          # old three-slot calibration
    header("CALIB", "SLIT,FP,FP,FP", SL),           # pre-manual slit type
    FakeFile({kwd.instrume: "ESPRESSO", kwd.dpr_catg: "SCIENCE",
              kwd.dpr_type: "OBJECT,SKY", kwd.dpr_tech: SL}),
    FakeFile({}),                                   # empty header
])
def test_rejected_by_all_raw_rules(f):
    assert not [r.classification for r in raw_rules() if r.is_classified(f)]


def test_static_tables_classified_by_pro_catg():
    for rule in (cls.hcl_lines_class, cls.std_star_table_class, cls.std_tell_table_class):
        assert rule.is_classified(FakeFile({kwd.pro_catg: rule.classification}))
        assert not rule.is_classified(FakeFile({kwd.pro_catg: "OTHER"}))
