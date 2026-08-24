# EDPS meta-targets — convention and ANDES usage

## What a meta-target is

A meta-target is a label attached to a task (`task.with_meta_targets([...])`).
It groups related tasks so you can select them together on the command line,
and it is the hook the QCFlow and CalChecker applications use to find tasks.

**Meta-targets do not affect the reduction graph, associations, or product
flow.** They only control (a) which subset of tasks a run targets and (b)
what the QC/monitoring apps see. `edps -m <meta-target>` runs the tasks in
that group *plus their dependency cascade*; with no `-m`, EDPS defaults to
`-m science` — i.e. the science tasks pull the whole calibration chain in as
dependencies regardless of how the cals are tagged.

Defining meta-targets is optional for a workflow to run, but **mandatory for
QCFlow and CalChecker** (design guide §4.2).

## The four predefined meta-targets

(from `edps_workflow_design_guide0.9.pdf` §4.2)

| Meta-target  | Meaning |
|--------------|---------|
| `QC1_CALIB`  | Tasks that create a master calibration or do instrument monitoring. |
| `QC0`        | Tasks run for a quick look at the telescope (QC0 process). |
| `SCIENCE`    | Tasks responsible for scientific reduction. |
| `CALCHECKER` | Tasks whose calibration completeness is monitored — "typically instrument monitoring, processing scientific and standard star exposures." |

Import them from `edps` (ESPRESSO also uses `IDP` for archive products; ANDES
does not currently).

## The CALCHECKER convention (the non-obvious one)

CALCHECKER is the "is the instrument calibrated and ready for tonight" monitor.
The key finding — verified against the reference ESPRESSO 3.3.0 workflow
(`~/pipes/espdr-3.3.0/workflows/`) — is that **CALCHECKER goes on both the
calibration producers *and* the science/standard-star consumers**, not just
one side. It is applied to:

1. The **consumers** — the science task and every standard-star task. In
   ESPRESSO `object` (science) is `[QC0, SCIENCE, CALCHECKER, IDP]` and
   `rv_stars` is `[CALCHECKER]`-only. These endpoints are the whole point of
   CalChecker: it walks *up* their association tree to check that the needed
   calibrations exist and are fresh.
2. The **routinely-monitored daily calibration producers** — but *not* all of
   them. ESPRESSO tags `mdark`, `led_ff`, `orderdef`, `mflat`, `eff_ab`,
   `wave_FP`, `wave_THAR` with CALCHECKER, and deliberately leaves `mbias`,
   `contam`, `cal_flux`, and **`wave_LFC`** as `QC1_CALIB`-only. LFC is the
   upgrade path, not the daily-monitored baseline, so it is excluded.

### ESPRESSO reference tagging (for comparison)

| Task | Meta-targets |
|------|--------------|
| mbias | `QC1_CALIB` |
| mdark | `QC1_CALIB, CALCHECKER` |
| detmon / contam | `QC1_CALIB` |
| led_ff, orderdef, mflat, eff_ab | `QC1_CALIB, CALCHECKER` |
| wave_FP, wave_THAR | `QC1_CALIB, CALCHECKER` |
| wave_LFC | `QC1_CALIB` |
| cal_flux | `QC1_CALIB` |
| rv_stars (standard) | `CALCHECKER` (only) |
| object (science) | `QC0, SCIENCE, CALCHECKER, IDP` |
| combine | `SCIENCE, IDP` |

## ANDES usage (as of 2026-08-24)

We aligned ANDES with the ESPRESSO convention. Current tagging in
`andes/andes_wkf.py`:

| Task | Meta-targets | Note |
|------|--------------|------|
| bias | `QC1_CALIB, CALCHECKER` | wider net than ESPRESSO (which omits CALCHECKER on bias); kept for VIS monitoring |
| dark | `QC1_CALIB, CALCHECKER` | |
| led | `QC1_CALIB, CALCHECKER` | matches led_ff |
| orderdef | `QC1_CALIB, CALCHECKER` | |
| slit | `QC1_CALIB, CALCHECKER` | no ESPRESSO analog; geometric monitored cal |
| flat | `QC1_CALIB, CALCHECKER` | |
| lsf | `QC1_CALIB, CALCHECKER` | no ESPRESSO analog; geometric monitored cal |
| wave_fp | `QC1_CALIB, CALCHECKER` | baseline wavelength cal |
| wave_lfc | `QC1_CALIB` | **no CALCHECKER** — LFC is the upgrade path, matching ESPRESSO's wave_LFC |
| rel_eff | `QC1_CALIB, CALCHECKER` | matches eff_ab |
| flux | `QC1_CALIB, CALCHECKER` | wider net than ESPRESSO (which omits CALCHECKER on cal_flux) |
| telluric | `QC1_CALIB, CALCHECKER` | standard-star consumer |
| science | `SCIENCE, CALCHECKER` | the blue box in the `-g2` graph |
| rv_std | `QC1_CALIB, CALCHECKER` | see decision below |

### Open decisions vs ESPRESSO

- **`rv_std` is `[QC1_CALIB, CALCHECKER]`**, whereas ESPRESSO's `rv_stars` is
  `[CALCHECKER]`-only. We keep `QC1_CALIB` because spec v1.2 treats the RV
  standard as a calibration product (it runs through `andes_science` as a QC1
  task, and shows green not blue in the graph). ESPRESSO's view is that a
  standard-star reduction is not a master-cal product. Reconcile if the
  consortium adopts the ESPRESSO reading.
- **bias / flux carry CALCHECKER** where ESPRESSO does not. Harmless (wider
  monitoring), but trim if we want an exact match.
- **QC0 and IDP unused.** Add QC0 to quick-look-at-telescope tasks and IDP to
  archive-product tasks if/when ANDES defines those.

## Graph colour reminder

In the `-g2` detailed graph, a box header is **deepskyblue3** iff its task
carries the `SCIENCE` meta-target, otherwise **green**. That is why `science`
is blue and `rv_std` (same `andes_science` recipe, but `QC1_CALIB`-tagged) is
green. Edge colours are per-source only (tracing), no semantic meaning.
