"""FITS header keywords used for classification, grouping and association."""

instrume = "instrume"
dpr_catg = "dpr.catg"
dpr_type = "dpr.type"
dpr_tech = "dpr.tech"
pro_catg = "pro.catg"

seq_arm = "seq.arm"      # spectrograph: UBV, RIZ, YJH, K
ins_mode = "ins.mode"    # observing mode: SL-UNI, IFU-AO
det_binx = "det.binx"
det_biny = "det.biny"

# calibration fibre (C) source: FP, HCL, LFC, LAMP or OFF. The Templates
# Manual (E-AND-SW-MAN-06-00-001 v2.0) keeps C out of DPR.TYPE per
# ESO-044156 and mandates a dedicated keyword; the name is ours pending
# the ICD. Informational for recipes, not used in classification.
ins_calfib = "ins.calfib"

tpl_start = "tpl.start"
mjd_obs = "mjd-obs"

# detector setup: bias/dark/LED flats serve both observing modes of a spectrograph
det_setup = [instrume, seq_arm, det_binx, det_biny]

# instrument setup: echelle frames are additionally specific to the observing mode
inst_setup = det_setup + [ins_mode]
