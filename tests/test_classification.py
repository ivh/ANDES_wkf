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

# one sample header per expected tag
SAMPLES = {
    "BIAS": header("CALIB", "BIAS", "IMAGE"),
    "DARK": header("CALIB", "DARK", "IMAGE"),
    "LEDFF": header("TECHNICAL", "FLAT,LAMP", "IMAGE"),
    "ORDERDEF_A": header("CALIB", "ORDERDEF,LAMP,OFF,OFF", SL),
    "ORDERDEF_C": header("CALIB", "ORDERDEF,OFF,LAMP,OFF", SL),
    "ORDERDEF_B": header("CALIB", "ORDERDEF,OFF,OFF,LAMP", SL),
    "ORDERDEF_ACB": header("CALIB", "ORDERDEF,LAMP,LAMP,LAMP", SL),
    "ORDERDEF_IFU": header("CALIB", "ORDERDEF,LAMP", IFU),
    "SLIT": header("CALIB", "SLIT,FP,FP,FP", SL),
    "SLIT_IFU": header("CALIB", "SLIT,FP", IFU),
    "LSF": header("CALIB", "LSF,LFC,FP,LFC", SL),
    "LSF_IFU": header("CALIB", "LSF,LFC", IFU),
    "FLAT_A": header("CALIB", "FLAT,LAMP,OFF,OFF", SL),
    "FLAT_C": header("CALIB", "FLAT,OFF,LAMP,OFF", SL),
    "FLAT_B": header("CALIB", "FLAT,OFF,OFF,LAMP", SL),
    "FLAT_ACB": header("CALIB", "FLAT,LAMP,LAMP,LAMP", SL),
    "FLAT_IFU": header("CALIB", "FLAT,LAMP", IFU),
    "WAVE_HCL_A": header("CALIB", "WAVE,HCL,FP,FP", SL),
    "WAVE_HCL_B": header("CALIB", "WAVE,FP,FP,HCL", SL),
    "WAVE_FP": header("CALIB", "WAVE,FP,FP,FP", SL),
    "WAVE_HCL_IFU": header("CALIB", "WAVE,HCL,FP", IFU),
    "WAVE_LFC": header("CALIB", "WAVE,LFC,FP,LFC", SL),
    "WAVE_LFC_IFU": header("CALIB", "WAVE,LFC,FP", IFU),
    "EFF": header("CALIB", "EFF,SKY,OFF,SKY", SL),
    "EFF_IFU": header("CALIB", "EFF,SKY", IFU),
    "STD_FLUX": header("CALIB", "STD,FLUX,OFF,SKY", SL),
    "STD_FLUX_IFU": header("CALIB", "STD,FLUX", IFU),
    "STD_TELLURIC": header("CALIB", "STD,SKY,OFF,TELLURIC", SL),
    "STD_TELLURIC_IFU": header("CALIB", "STD,TELLURIC", IFU),
    "STD_RV": header("CALIB", "STD,RV,FP,SKY", SL),
    "SCIENCE": header("SCIENCE", "OBJECT,FP,SKY", SL),
    "SCIENCE_IFU": header("SCIENCE", "OBJECT", IFU),
}


@pytest.mark.parametrize("tag", SAMPLES)
def test_sample_classifies_as_exactly_its_tag(tag):
    matches = {r.classification for r in raw_rules() if r.is_classified(SAMPLES[tag])}
    assert matches == {tag}


@pytest.mark.parametrize("dpr_type,tech", [
    ("OBJECT,FP,SKY", SL),
    ("SKY,FP,OBJECT", SL),                      # swapped counterpart
    ("OBJECT,FP,SKY", SL + ",SWAPPING"),
    ("OBJECT,DARK,SKY", SL),                    # no simultaneous reference
    ("OBJECT,LFC,SKY", SL + ",OFFSET"),
    ("SKY,FP,SKY", SL),                         # sky-only offset exposure
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
    header("CALIB", "OBJECT,FP,SKY", SL),           # wrong category
    header("SCIENCE", "OBJECT,FLAT,SKY", SL),       # invalid simcal source
    header("SCIENCE", "OBJECT,FP,SKY,SKY", SL),     # too many slots
    header("SCIENCE", "OBJECT,FP,SKY", IFU),        # SL pattern with IFU tech
    FakeFile({kwd.instrume: "ESPRESSO", kwd.dpr_catg: "SCIENCE",
              kwd.dpr_type: "OBJECT,FP,SKY", kwd.dpr_tech: SL}),
    FakeFile({}),                                   # empty header
])
def test_rejected_by_all_raw_rules(f):
    assert not [r.classification for r in raw_rules() if r.is_classified(f)]


def test_static_tables_classified_by_pro_catg():
    for rule in (cls.hcl_lines_class, cls.std_star_table_class, cls.std_tell_table_class):
        assert rule.is_classified(FakeFile({kwd.pro_catg: rule.classification}))
        assert not rule.is_classified(FakeFile({kwd.pro_catg: "OTHER"}))
