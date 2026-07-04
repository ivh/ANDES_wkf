"""ANDES EDPS workflow: tasks and subworkflows.

Every reduction chain follows the modular recipe design of the DRL
specification: raw frames pass through andes_util_detcal (and where
applicable andes_util_bkgr / andes_util_extract) before the recipe that
produces the master calibration or science product. One task chain per
recipe; spectrographs, binnings and observing modes are separated by the
setup keywords on the data sources, not by dedicated tasks.
"""

from edps import task, subworkflow, alternative_associated_inputs
from edps import SCIENCE, QC1_CALIB, CALCHECKER

from . import andes_datasources as ds
from . import andes_classification as cls

# max_ret=-1 means "no upper limit" (EDPS turns it into sys.maxsize)
ALL = -1


def detcal_task(name, raw, bias_task=None, dark_task=None, led_task=None):
    """Detector-signature cleaning step common to all chains.

    The detector calibrations are optional associations (min_ret=0): which
    of them exist depends on the arm (e.g. no bias for the NIR detectors).
    """
    builder = (task(name)
               .with_recipe("andes_util_detcal")
               .with_main_input(raw))
    if bias_task is not None:
        builder.with_associated_input(bias_task,
                                      [cls.master_bias_class, cls.master_bias_res_class],
                                      min_ret=0, max_ret=ALL)
    if dark_task is not None:
        builder.with_associated_input(dark_task,
                                      [cls.master_dark_class, cls.hot_pixel_mask_class],
                                      min_ret=0, max_ret=ALL)
    if led_task is not None:
        builder.with_associated_input(led_task,
                                      [cls.bad_pixel_mask_class, cls.detflat_class,
                                       cls.detlin_class],
                                      min_ret=0, max_ret=ALL)
    return builder.build()


def bkgr_task(name, main, orderdef_task):
    return (task(name)
            .with_recipe("andes_util_bkgr")
            .with_main_input(main)
            .with_associated_input(orderdef_task, cls.order_table_classes,
                                   min_ret=1, max_ret=ALL)
            .build())


def extract_task(name, main, orderdef_task, slit_task, flat_task=None):
    builder = (task(name)
               .with_recipe("andes_util_extract")
               .with_main_input(main)
               .with_associated_input(orderdef_task, cls.order_table_classes,
                                      min_ret=1, max_ret=ALL)
               .with_associated_input(slit_task, cls.slit_curve_classes,
                                      min_ret=1, max_ret=ALL))
    if flat_task is not None:
        builder.with_associated_input(flat_task,
                                      cls.order_profile_classes + cls.master_flat_classes
                                      + cls.blaze_classes,
                                      min_ret=1, max_ret=ALL)
    return builder.build()


def wave_alternatives(wave_fp_task, wave_lfc_task):
    # FP+HCL is the instrument baseline, the LFC a possible upgrade
    return (alternative_associated_inputs()
            .with_associated_input(wave_fp_task, cls.wave_product_classes, max_ret=ALL)
            .with_associated_input(wave_lfc_task, cls.wave_product_classes, max_ret=ALL))


# --- detector characterization ------------------------------------------

bias_task = (task("bias")
             .with_recipe("andes_cal_bias")
             .with_main_input(ds.bias)
             .with_meta_targets([QC1_CALIB, CALCHECKER])
             .build())


@subworkflow("dark", "")
def dark_swkf(bias_task):
    detcal = detcal_task("dark_detcal", ds.dark, bias_task)
    return (task("dark")
            .with_recipe("andes_cal_dark")
            .with_main_input(detcal)
            .with_meta_targets([QC1_CALIB, CALCHECKER])
            .build())


dark_task = dark_swkf(bias_task)


@subworkflow("led", "")
def led_swkf(bias_task, dark_task):
    detcal = detcal_task("led_detcal", ds.ledff, bias_task, dark_task)
    return (task("led")
            .with_recipe("andes_cal_led")
            .with_main_input(detcal)
            .with_meta_targets([QC1_CALIB])
            .build())


led_task = led_swkf(bias_task, dark_task)

# --- geometric calibration ------------------------------------------------


@subworkflow("orderdef", "")
def orderdef_swkf(bias_task, dark_task, led_task):
    detcal = detcal_task("orderdef_detcal", ds.orderdef, bias_task, dark_task, led_task)
    return (task("orderdef")
            .with_recipe("andes_cal_orderdef")
            .with_main_input(detcal)
            .with_meta_targets([QC1_CALIB])
            .build())


orderdef_task = orderdef_swkf(bias_task, dark_task, led_task)


@subworkflow("slit", "")
def slit_swkf(bias_task, dark_task, led_task, orderdef_task):
    detcal = detcal_task("slit_detcal", ds.slit, bias_task, dark_task, led_task)
    return (task("slit")
            .with_recipe("andes_cal_slit")
            .with_main_input(detcal)
            .with_associated_input(orderdef_task, cls.order_table_classes,
                                   min_ret=1, max_ret=ALL)
            .with_meta_targets([QC1_CALIB])
            .build())


slit_task = slit_swkf(bias_task, dark_task, led_task, orderdef_task)

# --- spectroscopic calibration ---------------------------------------------


@subworkflow("flat", "")
def flat_swkf(bias_task, dark_task, led_task, orderdef_task, slit_task):
    detcal = detcal_task("flat_detcal", ds.flat, bias_task, dark_task, led_task)
    # bootstrap: the flat's own extraction runs without flat-field inputs
    extract = extract_task("flat_extract", detcal, orderdef_task, slit_task)
    return (task("flat")
            .with_recipe("andes_cal_flat")
            .with_main_input(extract)
            .with_associated_input(detcal, min_ret=1, max_ret=ALL)
            .with_meta_targets([QC1_CALIB, CALCHECKER])
            .build())


flat_task = flat_swkf(bias_task, dark_task, led_task, orderdef_task, slit_task)


@subworkflow("lsf", "")
def lsf_swkf(bias_task, dark_task, led_task, orderdef_task, slit_task):
    detcal = detcal_task("lsf_detcal", ds.lsf, bias_task, dark_task, led_task)
    return (task("lsf")
            .with_recipe("andes_cal_LSF")
            .with_main_input(detcal)
            .with_associated_input(orderdef_task, cls.order_table_classes,
                                   min_ret=1, max_ret=ALL)
            .with_associated_input(slit_task, cls.slit_curve_classes,
                                   min_ret=1, max_ret=ALL)
            .with_meta_targets([QC1_CALIB])
            .build())


lsf_task = lsf_swkf(bias_task, dark_task, led_task, orderdef_task, slit_task)


@subworkflow("wavecal_fp", "")
def wave_fp_swkf(bias_task, dark_task, led_task, orderdef_task, slit_task, flat_task, lsf_task):
    detcal = detcal_task("wave_fp_detcal", ds.wave_fp, bias_task, dark_task, led_task)
    extract = extract_task("wave_fp_extract", detcal, orderdef_task, slit_task, flat_task)
    return (task("wave_fp")
            .with_recipe("andes_cal_wave_FP")
            .with_main_input(extract)
            # the cleaned 2D frames are needed for raw-frame line fitting
            .with_associated_input(detcal, min_ret=1, max_ret=ALL)
            .with_associated_input(ds.hcl_lines)
            .with_associated_input(lsf_task, cls.lsf_model_classes, min_ret=0, max_ret=ALL)
            .with_meta_targets([QC1_CALIB, CALCHECKER])
            .build())


wave_fp_task = wave_fp_swkf(bias_task, dark_task, led_task, orderdef_task, slit_task,
                            flat_task, lsf_task)


@subworkflow("wavecal_lfc", "")
def wave_lfc_swkf(bias_task, dark_task, led_task, orderdef_task, slit_task, flat_task, lsf_task):
    detcal = detcal_task("wave_lfc_detcal", ds.wave_lfc, bias_task, dark_task, led_task)
    extract = extract_task("wave_lfc_extract", detcal, orderdef_task, slit_task, flat_task)
    return (task("wave_lfc")
            .with_recipe("andes_cal_wave_LFC")
            .with_main_input(extract)
            .with_associated_input(detcal, min_ret=1, max_ret=ALL)
            .with_associated_input(lsf_task, cls.lsf_model_classes, min_ret=0, max_ret=ALL)
            .with_meta_targets([QC1_CALIB, CALCHECKER])
            .build())


wave_lfc_task = wave_lfc_swkf(bias_task, dark_task, led_task, orderdef_task, slit_task,
                              flat_task, lsf_task)

# --- cross-calibration ------------------------------------------------------


@subworkflow("rel_eff", "")
def rel_eff_swkf(bias_task, dark_task, led_task, orderdef_task, slit_task, flat_task):
    detcal = detcal_task("eff_detcal", ds.eff, bias_task, dark_task, led_task)
    extract = extract_task("eff_extract", detcal, orderdef_task, slit_task, flat_task)
    return (task("rel_eff")
            .with_recipe("andes_cal_rel_eff")
            .with_main_input(extract)
            .with_meta_targets([QC1_CALIB])
            .build())


rel_eff_task = rel_eff_swkf(bias_task, dark_task, led_task, orderdef_task, slit_task, flat_task)


@subworkflow("flux", "")
def flux_swkf(bias_task, dark_task, led_task, orderdef_task, slit_task, flat_task,
              wave_fp_task, wave_lfc_task):
    detcal = detcal_task("flux_detcal", ds.std_flux, bias_task, dark_task, led_task)
    bkgr = bkgr_task("flux_bkgr", detcal, orderdef_task)
    extract = extract_task("flux_extract", bkgr, orderdef_task, slit_task, flat_task)
    return (task("flux")
            .with_recipe("andes_cal_flux")
            .with_main_input(extract)
            .with_alternative_associated_inputs(wave_alternatives(wave_fp_task, wave_lfc_task))
            .with_associated_input(ds.std_star_table)
            .with_meta_targets([QC1_CALIB, CALCHECKER])
            .build())


flux_task = flux_swkf(bias_task, dark_task, led_task, orderdef_task, slit_task, flat_task,
                      wave_fp_task, wave_lfc_task)


@subworkflow("telluric", "")
def telluric_swkf(bias_task, dark_task, led_task, orderdef_task, slit_task, flat_task,
                  wave_fp_task, wave_lfc_task):
    detcal = detcal_task("telluric_detcal", ds.std_telluric, bias_task, dark_task, led_task)
    bkgr = bkgr_task("telluric_bkgr", detcal, orderdef_task)
    extract = extract_task("telluric_extract", bkgr, orderdef_task, slit_task, flat_task)
    return (task("telluric")
            .with_recipe("andes_cal_telluric_std")
            .with_main_input(extract)
            .with_alternative_associated_inputs(wave_alternatives(wave_fp_task, wave_lfc_task))
            .with_associated_input(ds.std_tell_table)
            .with_meta_targets([QC1_CALIB])
            .build())


telluric_task = telluric_swkf(bias_task, dark_task, led_task, orderdef_task, slit_task,
                              flat_task, wave_fp_task, wave_lfc_task)

# --- science reduction -----------------------------------------------------


def science_chain(name, raw, meta_targets, bias_task, dark_task, led_task, orderdef_task,
                  slit_task, flat_task, wave_fp_task, wave_lfc_task, rel_eff_task,
                  flux_task, telluric_task):
    """Full science-type reduction; also used for RV standard stars."""
    detcal = detcal_task(name + "_detcal", raw, bias_task, dark_task, led_task)
    bkgr = bkgr_task(name + "_bkgr", detcal, orderdef_task)
    extract = extract_task(name + "_extract", bkgr, orderdef_task, slit_task, flat_task)
    return (task(name)
            .with_recipe("andes_science")
            .with_main_input(extract)
            .with_alternative_associated_inputs(wave_alternatives(wave_fp_task, wave_lfc_task))
            .with_associated_input(rel_eff_task, cls.rel_eff_classes, min_ret=0, max_ret=ALL)
            .with_associated_input(flux_task, cls.abs_eff_classes, min_ret=0, max_ret=ALL)
            .with_associated_input(telluric_task, [cls.tell_model_class], min_ret=0, max_ret=ALL)
            .with_meta_targets(meta_targets)
            .build())


science_swkf = subworkflow("science", "")(science_chain)
rv_std_swkf = subworkflow("rv_std", "")(science_chain)

science_task = science_swkf("science", ds.science, [SCIENCE],
                            bias_task, dark_task, led_task, orderdef_task, slit_task,
                            flat_task, wave_fp_task, wave_lfc_task, rel_eff_task,
                            flux_task, telluric_task)

rv_std_task = rv_std_swkf("rv_std", ds.std_rv, [QC1_CALIB],
                          bias_task, dark_task, led_task, orderdef_task, slit_task,
                          flat_task, wave_fp_task, wave_lfc_task, rel_eff_task,
                          flux_task, telluric_task)
