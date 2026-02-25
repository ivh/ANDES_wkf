from edps import SCIENCE, QC1_CALIB, QC0, CALCHECKER
from edps import task, data_source, classification_rule, subworkflow

# --- Classification rules ---

bias_class = classification_rule("BIAS",
                                    {"instrume":"ANDES",
                                     "dpr.catg": "CALIB",
                                     "dpr.type":"BIAS",
                                     "dpr.tech":"IMAGE,RIZ",
                                     })

dark_class = classification_rule("DARK",
                                    {"instrume":"ANDES",
                                     "dpr.catg": "CALIB",
                                     "dpr.type":"DARK",
                                     "dpr.tech":"IMAGE,RIZ",
                                     })

led_class = classification_rule("LED",
                                    {"instrume":"ANDES",
                                     "dpr.catg": "CALIB",
                                     "dpr.type":"LED",
                                     "dpr.tech":"IMAGE,RIZ",
                                     })

ordef_class = classification_rule("ORDEF",
                                    {"instrume":"ANDES",
                                     "dpr.catg": "CALIB",
                                     "dpr.type":"ORDERDEF,FLAT,FLAT,FLAT",
                                     "dpr.tech":"ECHELLE,RIZ",
                                     })

slitdef_class = classification_rule("SLITDEF",
                                    {"instrume":"ANDES",
                                     "dpr.catg": "CALIB",
                                     "dpr.type":"SLITDEF,FP,FP,FP",
                                     "dpr.tech":"ECHELLE,RIZ",
                                     })

flat_class = classification_rule("FLAT",
                                {"instrume":"ANDES",
                                 "dpr.catg":"CALIB",
                                 "dpr.type":"FLAT,FLAT,FLAT",
                                 "dpr.tech":"ECHELLE,RIZ",
                                 })

wave_class = classification_rule("WAVE",
                                {"instrume":"ANDES",
                                 "dpr.catg":"CALIB",
                                 "dpr.type":"WAVE,FP,FP,FP",
                                 "dpr.tech":"ECHELLE,RIZ",
                                 })

contam_class = classification_rule("CONTAM",
                                {"instrume":"ANDES",
                                 "dpr.catg":"CALIB",
                                 "dpr.type":"DARK,FP,DARK",
                                 "dpr.tech":"ECHELLE,RIZ",
                                 })

science_class = classification_rule("SCIENCE",
                                {"instrume":"ANDES",
                                 "dpr.catg":"SCIENCE",
                                 "dpr.type":"OBJECT,FP,SKY",
                                 "dpr.tech":"ECHELLE,RIZ",
                                 })


# --- Data sources ---

bias = (data_source()
            .with_classification_rule(bias_class)
            .with_match_keywords(["instrume"])
            .build())

dark = (data_source()
            .with_classification_rule(dark_class)
            .with_match_keywords(["instrume"])
            .build())

flat = (data_source()
            .with_classification_rule(flat_class)
            .with_match_keywords(["instrume"])
            .build())

wave = (data_source()
            .with_classification_rule(wave_class)
            .with_match_keywords(["instrume"])
            .build())

science_sl = (data_source()
            .with_classification_rule(science_class)
            .with_match_keywords(["instrume"])
            .build())


# --- Processing tasks ---

bias_task = (task('bias')
            .with_recipe("andes_cal_bias")
            .with_main_input(bias)
            .build())

@subworkflow("dark", "")
def dark_swkf(bias_task):
    detcal = (task("dark_detcal")
        .with_recipe("andes_util_detcal")
        .with_main_input(dark)
        .with_associated_input(bias_task)
        .build())
    return (task("dark")
        .with_recipe("andes_cal_dark")
        .with_main_input(detcal)
        .build())

dark_task = dark_swkf(bias_task)

@subworkflow("flat", "")
def flat_swkf(bias_task, dark_task):
    detcal = (task("flat_detcal")
        .with_recipe("andes_util_detcal")
        .with_main_input(flat)
        .with_associated_input(bias_task)
        .with_associated_input(dark_task)
        .build())
    extract = (task("flat_extract")
        .with_recipe("andes_util_extract")
        .with_main_input(detcal)
        .build())
    return (task("flat")
        .with_recipe("andes_cal_flat")
        .with_main_input(extract)
        .build())

flat_task = flat_swkf(bias_task, dark_task)

@subworkflow("wavecal", "")
def wavecal_swkf(bias_task, dark_task, flat_task):
    detcal = (task("wave_detcal")
        .with_recipe("andes_util_detcal")
        .with_main_input(wave)
        .with_associated_input(bias_task)
        .with_associated_input(dark_task)
        .build())
    extract = (task("wave_extract")
        .with_recipe("andes_util_extract")
        .with_main_input(detcal)
        .with_associated_input(flat_task)
        .build())
    return (task("wavecal")
        .with_recipe("andes_cal_wave_FP")
        .with_main_input(extract)
        .build())

wavecal_task = wavecal_swkf(bias_task, dark_task, flat_task)

@subworkflow("science", "")
def science_swkf(bias_task, dark_task, flat_task, wavecal_task):
    detcal = (task("sci_detcal")
        .with_recipe("andes_util_detcal")
        .with_main_input(science_sl)
        .with_associated_input(bias_task)
        .with_associated_input(dark_task)
        .build())
    bkgr = (task("sci_bkgr")
        .with_recipe("andes_util_bkgr")
        .with_main_input(detcal)
        .build())
    extract = (task("sci_extract")
        .with_recipe("andes_util_extract")
        .with_main_input(bkgr)
        .with_associated_input(flat_task)
        .build())
    return (task("science")
        .with_recipe("andes_science")
        .with_main_input(extract)
        .with_associated_input(wavecal_task)
        .with_meta_targets([SCIENCE])
        .build())

science_task = science_swkf(bias_task, dark_task, flat_task, wavecal_task)
