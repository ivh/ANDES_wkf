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

tpl_start = "tpl.start"
mjd_obs = "mjd-obs"

# detector setup: bias/dark/LED flats serve both observing modes of a spectrograph
det_setup = [instrume, seq_arm, det_binx, det_biny]

# instrument setup: echelle frames are additionally specific to the observing mode
inst_setup = det_setup + [ins_mode]
