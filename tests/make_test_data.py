"""Generate a synthetic night of ANDES raw data from calibration_plan.yaml.

Reads the canonical plan -- the same file the E2E simulator's `andes-sim night`
consumes -- so the DPR grammar has a single source and cannot drift from the
workflow's classification rules. Writes header-only frames for fast CI and
manual edps runs (-c, -od, -t); real-pixel frames come from the simulator.

The plan is walked the way night.py walks it, but header-only, single VIS
config and single IFU scale, with exposure counts capped. After writing, every
frame is classified with the workflow's own rules and a coverage report is
printed, so plan<->workflow gaps (unclassifiable planned types, reconciliation
items 1/2/4) are surfaced rather than hidden.

Usage: uv run python tests/make_test_data.py <output_dir> [--arms RIZ,YJH]
"""

import argparse
import itertools
import sys
from pathlib import Path

import yaml
from astropy.io import fits

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from andes import andes_classification as cls          # noqa: E402
from andes import andes_keywords as kwd                # noqa: E402
from edps.generator.classif_rule import BaseClassificationRule  # noqa: E402

PLAN_PATH = REPO_ROOT / "calibration_plan.yaml"
DEFAULT_ARMS = ["RIZ", "YJH"]   # one VIS (has bias), one NIR (no bias) + IFU
NEXP_CAP = 3                    # header-only frames: a few per group is plenty

counter = itertools.count(1)


def long_key(key):
    return "HIERARCH ESO " + key.upper().replace(".", " ") if "." in key else key.upper()


def write_frame(outdir, mjd, kws):
    hdu = fits.PrimaryHDU()
    hdu.header["INSTRUME"] = "ANDES"
    hdu.header["MJD-OBS"] = mjd
    for key, value in kws.items():
        if value is not None:
            hdu.header[long_key(key)] = value
    name = f"ANDES_{kws.get('seq.arm', 'X')}_{next(counter):04d}.fits"
    hdu.writeto(Path(outdir) / name, overwrite=True)


def frame(arm, dpr_type, catg, tech, mode=None, calfib=None, mask=None):
    return {"seq.arm": arm, "dpr.catg": catg, "dpr.type": dpr_type,
            "dpr.tech": tech, "ins.mode": mode, "ins.calfib": calfib,
            "ins.mask": mask, "det.binx": 1, "det.biny": 1}


def _n(exp):
    n = exp.get("n", 1)
    return min(n, NEXP_CAP) if isinstance(n, int) else NEXP_CAP


def _mode_for(applies, tech):
    modes = applies.get("modes")
    if modes:
        return modes[0]
    return "IFU-AO" if tech and "IFU" in tech else "SL-UNI"


def plan_frames(plan, arms):
    """Yield (group, frame-dict) for every planned exposure, plan grammar verbatim."""
    for proc in plan.get("procedures", []):
        if "reference" in proc:                       # when-used config repeats
            continue
        applies = proc.get("applies_to", {})
        proc_arms = applies.get("arms", arms)
        dpr = proc.get("dpr", {})
        tpl = proc.get("template")
        for arm in arms:
            if arm not in proc_arms:
                continue
            for exp in proc.get("exposures", []):
                tech = exp.get("tech") or dpr.get("tech")
                mode = _mode_for(applies, tech)
                if mode == "IFU-AO" and arm != "YJH":
                    continue
                kw = exp.get("keywords", {})
                yield (f"{arm}:{tpl}:{mode}", exp, _n(exp),
                       frame(arm, exp["type"], dpr.get("catg"), tech, mode,
                             kw.get("ins.calfib"), kw.get("ins.mask")))

    for entry in plan.get("night_calibrations", []):
        if entry.get("status") == "upgrade" or not entry.get("exposures"):
            continue
        dpr = entry.get("dpr", {})
        tpl = entry.get("template") or entry.get("name")
        for arm in arms:
            for exp in entry.get("exposures", []):
                tech = exp.get("tech") or dpr.get("tech")
                mode = "IFU-AO" if tech and "IFU" in tech else "SL-UNI"
                if mode == "IFU-AO" and arm != "YJH":
                    continue
                kw = exp.get("keywords", {})
                yield (f"{arm}:{tpl}:{mode}", exp, _n(exp),
                       frame(arm, exp["type"], dpr.get("catg"), tech, mode,
                             kw.get("ins.calfib")))

    for entry in plan.get("observations", []):
        dpr = entry.get("dpr", {})
        tpl = (entry.get("templates") or [entry.get("name")])[0]
        for arm in arms:
            for exp in entry.get("exposures", []):
                tech = exp.get("tech") or dpr.get("tech")
                mode = "IFU-AO" if tech and "IFU" in tech else "SL-UNI"
                if mode == "IFU-AO" and arm != "YJH":
                    continue
                kw = exp.get("keywords", {})
                yield (f"{arm}:{entry.get('name')}:{mode}", exp, _n(exp),
                       frame(arm, exp["type"], dpr.get("catg"), tech, mode,
                             kw.get("ins.calfib")))


def static_tables(arms):
    for arm in arms:
        for catg in ("HCL_LINES_TABLE", "STD_STAR_TABLE", "STD_TELL_TABLE"):
            yield {"seq.arm": arm, "pro.catg": catg}


def raw_rules():
    return [v for v in vars(cls).values()
            if isinstance(v, BaseClassificationRule) and not v.is_product()]


class _F(dict):
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def __getitem__(self, k): return self.get(k)


def classify(kws):
    f = _F({kwd.instrume: "ANDES", kwd.dpr_catg: kws.get("dpr.catg"),
            kwd.dpr_type: kws.get("dpr.type"), kwd.dpr_tech: kws.get("dpr.tech"),
            kwd.pro_catg: kws.get("pro.catg")})
    return {r.classification for r in raw_rules() if r.is_classified(f)}


def report(rows):
    ok = [r for r in rows if len(r[1]) == 1]
    ambiguous = [r for r in rows if len(r[1]) > 1]
    missing = sorted({r[0] for r in rows if not r[1]})
    print(f"\ncoverage: {len(ok)}/{len(rows)} frames classify to exactly one tag")
    if missing:
        print("  UNCLASSIFIED planned types (plan<->workflow gaps):")
        for t in missing:
            print(f"    - {t}")
    if ambiguous:
        print("  AMBIGUOUS (matched >1 rule):")
        for t, tags in {r[0]: r[1] for r in ambiguous}.items():
            print(f"    - {t} -> {sorted(tags)}")
    tags = sorted({next(iter(m)) for _, m in ok})
    print(f"  tags exercised: {', '.join(tags)}")


def main(outdir, arms):
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    plan = yaml.safe_load(PLAN_PATH.read_text())

    rows, mjd = [], 61000.0
    for group, _exp, n, kws in plan_frames(plan, arms):
        for _ in range(n):
            write_frame(outdir, mjd, {**kws, "tpl.start": group})
            mjd += 0.001
        rows.append((f"{kws['dpr.catg']} {kws['dpr.type']} [{kws['dpr.tech']}]",
                     classify(kws)))
    for kws in static_tables(arms):
        write_frame(outdir, mjd, {**kws, "tpl.start": f"{kws['seq.arm']}-static"})
        mjd += 0.001

    print(f"wrote {next(counter) - 1} files to {outdir} for arms {arms}")
    report(rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir", nargs="?", default="test_data")
    ap.add_argument("--arms", default=",".join(DEFAULT_ARMS))
    args = ap.parse_args()
    main(args.outdir, [a for a in args.arms.split(",") if a])
