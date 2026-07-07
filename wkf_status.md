# ANDES EDPS Workflow — Status

High-level progress log of the workflow implementation, one "round" per major iteration.

## Round 0 — Initial mock-up

Starting point before the full implementation:

- Single-file `andes/andes_wkf.py` with RIZ-only chains for dark, flat, wavecal (FP)
  and science, demonstrating the modular detcal/extract/bkgr subworkflow pattern.
- Classification rules hard-coded the spectrograph into `DPR.TECH` (`ECHELLE,RIZ`),
  association matched on `instrume` only.
- An invented `SLITDEF` raw type for slit characterization; contamination task
  from an older spec version still referenced in the docs.
- No tests, no recipe plugins, no parameters file.

## Round 1 — Full workflow per spec v1.2

Implemented the complete reduction cascade from the DRL specification
(E-AND-SW-SPE-09-00-002 v1.2), after resolving the naming inconsistencies found
between the spec's raw-data table, frame-type descriptions and recipe chapters.

### Naming scheme (resolved)

- 1:1 correspondence between raw `DPR.TYPE` kinds, templates and recipes
  (guiding principle). New dedicated kinds `SLIT`, `LSF`, `EFF` so that
  cal_slit/cal_LSF/cal_rel_eff no longer compete with other recipes for frames.
- `DPR.TYPE` grammar: `<KIND>,<A>,<C>,<B>` for echelle calibrations, plain
  `<A>,<C>,<B>` for science; sub-slit order is A, C, B (calibration fibre in
  the middle). IFU frames use single-slot forms (`FLAT,LAMP`, `OBJECT`).
- Spectrograph removed from `DPR.TECH`; setup is carried by `seq.arm`,
  `ins.mode`, `det.binx/y`. One generic task graph serves all arms, binnings
  and both observing modes — no per-spectrograph code.
- Products carry per-slit suffixes (`_A/_B/_C/_IFU`) and origin prefixes where
  several recipes produce the same kind of product (`S1D_WAVE_*`,
  `S1D_STD_FLUX_*`, ...; bare `S1D_*`/`SS1D_*` reserved for science).
  Collisions fixed: `MASTER_FLAT_<slit>` (vs raw FLAT_A), `MASTER_BIAS_RES`,
  `ORDER_TABLE`/`SLIT_CURVE` (vs the ORDERDEF/SLITDEF input aliases),
  `WAVE_MATRIX_DRIFT_<slit>` for the science drift-corrected matrix.

### Implementation

- Workflow split per the ESO file convention: `andes_keywords.py`,
  `andes_rules.py`, `andes_classification.py`, `andes_datasources.py`,
  `andes_wkf.py`, `andes_parameters.yaml`.
- All 16 recipes of the spec as 39 tasks in 13 subworkflows: bias, dark, led,
  orderdef, slit, lsf, flat, wave_fp, wave_lfc, rel_eff, flux, telluric,
  science — plus `rv_std` as a second instantiation of the science chain
  (spec v1.2 routes RV standards through `andes_science`).
- Wavelength calibration FP/LFC modelled as EDPS alternatives (FP preferred).
  Static tables (HCL_LINES_TABLE, STD_STAR_TABLE, STD_TELL_TABLE) as data
  sources matched on instrument+arm.
- Dummy pyesorex recipes (`recipes/andes_dummy_recipes.py`) for all 16
  recipes: they write empty FITS products with correct `PRO.CATG` and
  inherited setup keywords, so the entire cascade executes for real.

### Validation

Two levels, with different mechanics:

- The pytest suite touches no FITS files at all: classification rules are
  called directly on fake header dicts, and the task-graph tests walk the
  in-memory task objects from importing the workflow.
- The end-to-end run uses real, tiny FITS files: `tests/make_test_data.py`
  writes header-only raw frames (no data arrays), and the real EDPS server
  classifies, groups and executes the cascade by invoking pyesorex with the
  dummy recipes. Each dummy recipe writes 2x2-pixel products with correct
  PRO.CATG and inherited setup keywords, which EDPS then classifies and feeds
  to the next task — the dataflow is fully real, only pixel content is fake.
  Job directories with SOFs, logs and products land under
  `$EDPS_base_dir/ANDES/<task>/<job-id>/`.

Results:

- 55 pytest tests: classification rules (every raw type classifies as exactly
  its tag; science variants incl. swapping; rejection cases) and task-graph
  structure (uniqueness, completeness, chain order, alternative preference).
- Synthetic data generator (`tests/make_test_data.py`): 86 frames covering
  RIZ SL-UNI (VIS, with bias), YJH SL-UNI (NIR, no bias) and YJH IFU-AO.
- EDPS classification: 86/86 files classified, none unclassified.
- Data organization: 98 jobs, all associations complete — bias associated for
  RIZ, correctly absent-but-optional for YJH; IFU jobs pick IFU calibrations.
- Full execution with dummy recipes: 98/98 jobs COMPLETED; the science SOF
  receives the complete calibration chain (wave products, REL_EFF, ABS_EFF,
  TELL_MODEL, per-slit extractions).

### Decisions flagged for review

1. Sub-slit order A,C,B and the SLIT/LSF/EFF raw kinds are additions/readings
   not (yet) in Table 2 of the spec — feed back into the document and AD4.
2. `WAVE,FP,FP,FP` frames assigned to `andes_cal_wave_FP` (unclaimed in spec).
3. LED flats kept as `TECHNICAL` / `FLAT,LAMP` per Table 2; `LED,LAMP` would
   be the stricter 1:1 choice.
4. `seq.arm` invented as spectrograph keyword (spec defines none; X-shooter
   precedent).
5. VIS/NIR differences handled by optional associations (`min_ret=0`) because
   EDPS conditions cannot see FITS keywords; a missing VIS bias currently
   passes silently. Revisit with per-arm parameter sets or assoc preferences.
6. Grouping assumes: one wave template takes all three exposure types; ABBA
   swap sequences share one `tpl.start`; multi-exposure science templates
   reduce as a single job (per-exposure reduction may be wanted).
7. EDPS passes all products of an associated job into the SOF; recipes must
   select what they need (or add `with_input_filter` later).
8. Parameter sets named `science_parameters`/`qc1_parameters` (EDPS client
   default); currently empty placeholders.

## Round 2 — Templates Manual grammar (2026-07-07)

Adapted the DPR grammar to the Templates Manual E-AND-SW-MAN-06-00-001 v2.0
(2026-05-18, newer than DRL spec v1.2), which contradicts the Round 1
reading; decision recorded as reconciliation item 10 in
`calibration_plan.yaml`.

- `DPR.TYPE` now carries two slots (first = fiber A, second = fiber B); the
  calibration fibre C moved to the dedicated keyword `ins.calfib`
  (FP/HCL/LFC/LAMP/OFF; name pending ICD, per ESO-044156 C must not be in
  DPR.TYPE). Not used in classification.
- Type changes: `SLITMASK,FP,OFF`/`SLITMASK,OFF,FP` (CALIB or TECHNICAL)
  replace `SLIT,...`; sky flats are `FLAT,SKY,SKY`/`FLAT,SKY` (were
  `EFF,...`; tag names EFF/EFF_IFU kept); WAVE split per slit
  (`WAVE,HCL,FP` = WAVE_HCL_A etc., LFC now WAVE_LFC_A/WAVE_LFC_B); IFU
  gains WAVE_FP_IFU and STD_RV_IFU; ORDERDEF/FLAT lose the C and ACB
  variants (C-fibre order definition and flat are open, reconciliation 2).
- No LSF raw type in the manual: the `lsf` task now consumes the SLITMASK
  frames (reconciliation 3); the LSF datasource is gone.
- Science: `OBJECT,SKY`/`SKY,OBJECT` (TS), `OBJECT,WAVE`/`WAVE,OBJECT`
  (TC, sim-cal lamp is a template parameter), IFU unchanged.
- `make_test_data.py` and the pytest samples rewritten accordingly
  (57 tests green). Real-pixel raw frames come from the E2E simulator
  (`andes-sim make-raw` / `night`), which follows the same grammar.

Execution validation (same day): a fresh E2E headers-only RIZ night
(86 frames + static tables) ran through the full cascade with the dummy
recipes — 40/40 jobs COMPLETED toward science, plus the 4-job rv_std
chain (44 total). The science SOF carries the complete calibration chain
(per-slit wave products incl. _C, WAVE_MAP, REL_EFF, ABS_EFF, TELL_MODEL,
extractions, line tables). Operational note: the EDPS *server* must be
started with PYESOREX_PLUGIN_DIR set (and without a foreign
ESOREX_PLUGIN_DIR); a server started from a shell lacking it makes every
job fail in pyesorex get_c_recipes — `edps -shutdown` first.

## Round 3 — first real recipe: andes_cal_bias (2026-07-07)

Replaced the andes_cal_bias dummy with a real implementation
(`recipes/andes_cal_bias.py`); its conventions are the template for the
other recipes:

- Products mirror the raw MEF layout: DFS-compliant header-only primary
  (cpl.dfs.save_propertylist; PRO.CATG, setup keywords, summary QC), one
  float32 extension per detector with per-extension QC.
- MASTER_BIAS = kappa-sigma-clipped per-pixel mean (MAD-based threshold:
  a plain std is too inflated by a single cosmic hit in a 10-stack to
  ever clip it); MASTER_BIAS_RES = per-pixel std across the stack (RON
  map). Parameters: kappa (5.0), clip_iterations (3).
- QC per extension: BIAS LEVEL, RON ADU, RON E (via the extension's gain
  keyword), MASTER RMS; NFRAMES on the primary.
- Validated closed-loop against the E2E simulator's injected detector
  truth (rawnights/riz_daily, 10 BIAS frames): level 1000.00 vs 1000,
  RON 6.92 e- vs 7.0 (~1% low from clip trimming at N=10), master RMS
  1.13 vs 1.11 ADU. Function-level pytest in tests/test_cal_bias.py
  (5 tests); EDPS run: bias -> dark_detcal consumes the real products.
- Runtime 206 s for 10 x 2 x 85 Mpx (masked-array clipping dominates;
  optimize later if it matters).
