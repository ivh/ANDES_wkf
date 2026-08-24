# ANDES EDPS Workflow Project

## What is ANDES

ANDES (ArmazoNes high Dispersion Echelle Spectrograph) is a modular high-resolution spectrograph for ESO's Extremely Large Telescope (ELT). It has four spectrographs covering different wavelength ranges:

- **UBV**: 0.35-0.63um
- **RIZ**: 0.62-0.95um
- **YJH**: 0.95-1.80um (NIR, uses HAWAII4RG detectors)
- **K**: 1.8-2.40um

Each spectrograph has multiple arms, each with its own detector. The instrument has two observing modes:

- **SL-UNI** (Seeing Limited): Common to all spectrographs. Two pseudo-slits (A and B) plus a calibration fibre. Light from ~30 fibres per aperture forms each pseudo-slit.
- **IFU-AO**: Currently only for YJH. Separate pseudo-slit from SL mode.

Key design aspects relevant to the DRS:
- Pseudo-slits are treated like long tilted/curved slits, not individual fibres (baseline for SL mode)
- Each spectrograph/mode/binning combination must be calibrated separately
- Data from different spectrographs are reduced independently, then combined at the end
- Swapping (ABBA nodding) is supported for sky subtraction in pixel-space

## What is EDPS

The ESO Data Processing System (EDPS) is ESO's framework for running data processing pipelines. It orchestrates "recipes" (standalone C/Python programs that process FITS data) by:

1. Classifying input files based on FITS header keywords
2. Associating calibrations to science data based on matching rules
3. Executing recipes in the correct sequence with proper inputs

EDPS workflows are written in Python using the `edps` library. The `pyesorex` package provides the recipe execution engine (`esorex`).

## Project Structure

```
edps/
  andes/
    __init__.py
    andes_wkf.py             # Tasks and subworkflows
    andes_datasources.py     # Data sources (grouping, matching)
    andes_classification.py  # Classification rules (raw, static, products)
    andes_rules.py           # Function-based classification rules
    andes_keywords.py        # Header keyword and setup-keyword definitions
    andes_parameters.yaml    # Workflow/recipe parameter sets
  recipes/                # pyesorex recipe plugins; real andes_cal_bias, rest dummies
  tests/                  # pytest suite + synthetic raw data generator
  docs/                   # EDPS docs + project notes (see index below)
  pyproject.toml          # uv project config
  .env                    # Sets PYESOREX_PLUGIN_DIR=./recipes
```

All commands use `uv run`, e.g. `uv run edps -lw` or `uv run pyesorex`.

### docs/ index

- `edps_workflow_design_guide0.9.pdf` — the reference for the `edps` API
  (classification, data sources, tasks, meta-targets §4.2, input/output
  filtering §4.3). First place to look for how a builder method behaves.
- `edps_tutorial0.9.3.pdf` — running EDPS end-to-end (uses ESPRESSO/KMOS as
  examples): targets/meta-targets on the command line, parameter sets, `-m`.
- `EDPS_workflow_design_tutorial___quick_start 1.pdf` — minimal FORS workflow
  built from scratch; good template for the overall file layout.
- `meta_targets.md` — meta-target convention (esp. CALCHECKER) and ANDES's
  tagging, distilled from the design guide + the ESPRESSO reference workflow.
- `meta_chat.txt` — early scoping Q&A about the project.

Reference pipeline for convention-checking: the installed ESPRESSO workflow at
`~/pipes/espdr-3.3.0/workflows/` (`espresso_wkf.py` etc.) — a real ESO EDPS
workflow to compare our choices against.

## EDPS Workflow Concepts

A workflow is a Python description of a data reduction pipeline. It defines:
- What types of files exist (classification rules)
- How files should be grouped (data sources)
- What processing steps to run and in what order (tasks)
- How to associate calibrations to each step (match keywords/functions)

### Classification Rules

A `classification_rule` maps FITS header keywords to a tag name. Files matching the rule get classified with that tag.

```python
from edps import classification_rule

bias_class = classification_rule("BIAS", {
    "instrume": "ANDES",
    "dpr.catg": "CALIB",
    "dpr.type": "BIAS",
    "dpr.tech": "IMAGE,RIZ",
})
```

The first argument is the tag (used in recipe input SOFs). The second is a dict of keyword-value pairs that a file's headers must match. For complex rules, pass a function instead of a dict.

### Data Sources

A `data_source` defines a group of input files for a task. It specifies:
- Which classification rule(s) the files must satisfy
- How to group files together (grouping keywords)
- How to associate this data source to tasks (match keywords or functions)

```python
from edps import data_source

bias = (data_source()
    .with_classification_rule(bias_class)
    .with_grouping_keywords(["tpl.start"])
    .with_match_keywords(["instrume"])
    .build())
```

Key methods:
- `.with_classification_rule(rule)` - which files belong here
- `.with_grouping_keywords(["kwd1", "kwd2"])` - how to group files for processing together
- `.with_match_keywords(kwds)` - simple association: match these keywords between science and calibration
- `.with_match_function(func)` - complex association using a custom function
- `.with_min_group_size(n)` - minimum files needed in a group
- `.with_cluster("SKY.POSITION", min, max)` - cluster by proximity of a parameter
- `.build()` - finalize

### Tasks

A `task` is a processing step that runs a recipe on grouped input data.

```python
from edps import task

bias_task = (task("bias")
    .with_recipe("andes_cal_bias")
    .with_main_input(bias)
    .build())

flat_task = (task("flat")
    .with_recipe("andes_cal_flat")
    .with_main_input(flat)
    .with_associated_input(bias_task)
    .build())
```

Key methods:
- `.with_recipe("recipe_name")` - the pipeline recipe to execute
- `.with_main_input(data_source_or_task)` - primary input data
- `.with_associated_input(task_or_datasource)` - calibration inputs (can chain multiple)
- `.with_meta_targets([SCIENCE, QC1_CALIB])` - tag task for QC/science targeting
- `.with_condition(func)` - only execute if condition is true
- `.with_input_filter(rule, mode="SELECT"|"REJECT")` - filter products passed to recipe
- `.with_output_filter(rule, mode="SELECT"|"REJECT")` - filter products passed downstream
- `.with_job_processing(func)` - modify job properties at runtime
- `.with_dynamic_parameter("name", func)` - compute parameter from input data
- `.with_alternatives(alt)` - specify fallback calibration inputs
- `.build()` - finalize

Convention for method order: recipe, main input, associated inputs (following calibration cascade), execution condition, dynamic parameters, job functions, filters, mapping categories, meta targets.

### Subworkflows

A `@subworkflow` decorator wraps a function that returns a task. It creates a reusable sub-pipeline that can be used as input to another task.

```python
from edps import subworkflow

@subworkflow("dark_prepare", "")
def dark_prepare(bias_task):
    return (task("bias_prepare")
        .with_main_input(dark)
        .with_associated_input(bias_task)
        .with_recipe("andes_detcal")
        .build())

dark_task = (task("dark")
    .with_main_input(dark_prepare(bias_task))
    .with_recipe("andes_cal_dark")
    .build())
```

### Metatargets

Predefined labels to group related tasks:
- `SCIENCE` - science reduction tasks
- `QC1_CALIB` - master calibration / instrument monitoring tasks
- `QC0` - quick-look tasks run at telescope
- `CALCHECKER` - calibration monitoring tasks

Selection-only (they don't affect associations/dataflow). The non-obvious
convention — CALCHECKER goes on both cal producers *and* science/standard
consumers, LFC excluded as upgrade path — plus ANDES's full tagging table and
the ESPRESSO reference are in `docs/meta_targets.md`. Read it before touching
`with_meta_targets`.

### Parameters File

`andes_parameters.yaml` (in the workflow directory) stores workflow and recipe parameters:

```yaml
qc1_parameters:
  is_default: yes
  workflow_parameters:
    param1: value1
  recipe_parameters:
    bias:
      andes_cal_bias.param1: value1
```

### Workflow File Naming Convention

For a full workflow package, files are named:
- `andes_wkf.py` - main workflow (tasks)
- `andes_datasources.py` - data source definitions
- `andes_classification.py` - classification rules
- `andes_rules.py` - complex classification/association functions
- `andes_keywords.py` - header keyword variable definitions
- `andes_task_functions.py` - auxiliary task functions
- `andes_parameters.yaml` - parameters

The workflow is split per this convention (no `andes_task_functions.py` yet; task-factory helpers live in `andes_wkf.py`).

### Running EDPS

```bash
uv run edps -lw                                               # list available workflows
uv run edps -w andes.andes_wkf -g | dot -Tpng > andes.png    # generate workflow graph (collapsed subworkflows)
uv run edps -w andes.andes_wkf -g2 | dot -Tpng > andes.png   # detailed graph (shows tasks inside subworkflows)
uv run edps -w andes.andes_wkf -i <data_dir> -t bias         # run bias task
uv run edps -w andes.andes_wkf -lt                            # list tasks in workflow
uv run edps -shutdown                                         # restart server after workflow changes
```

## ANDES Data Reduction Pipeline

### Reduction Cascade

The processing order (each step depends on products from previous steps):

1. **Detector characterization**
   - BIAS (VIS only) -> `andes_cal_bias` -> MASTER_BIAS, MASTER_BIAS_RES
   - DARK (VIS & NIR) -> `andes_cal_dark` -> MASTER_DARK, HOT_PIXEL_MASK
   - LED flat-field / gain / linearity -> `andes_cal_led` -> BAD_PIXEL_MASK, DETFLAT, DETLIN (linearity is part of cal_led; there is no separate `andes_cal_lin` in spec v1.2)
   - Detector calibration utility -> `andes_util_detcal` (applies bias, dark, gain, bad pixels, linearity to any raw frame)

2. **Geometric calibration**
   - Order definition -> `andes_cal_orderdef` -> ORDER_TABLE_<slit>
   - Slit characterization -> `andes_cal_slit` -> SLIT_CURVE_<slit> (tilt, curvature from FP/LFC lines)

3. **Spectroscopic calibration**
   - Flat-field, blaze, order profile -> `andes_cal_flat` -> MASTER_FLAT_<slit>, BLAZE_<slit>, ORDER_PROFILE_<slit>
   - LSF characterization -> `andes_cal_LSF` -> LSF_MODEL_<slit> (runs on the SLITMASK frames; no dedicated LSF raw type in the Templates Manual)
   - Wavelength calibration (FP) -> `andes_cal_wave_FP` -> WAVE_TABLE/WAVE_MATRIX/DLL_MATRIX/S1D_WAVE_<slit>, WAVE_MAP
   - Wavelength calibration (LFC) -> `andes_cal_wave_LFC` -> same products (alternative; FP is baseline)
   - Background subtraction -> `andes_util_bkgr` (inter-order scattered light)
   - Extraction -> `andes_util_extract` (uses ORDER_TABLE, SLIT_CURVE, MASTER_FLAT, BLAZE)

4. **Cross-calibration**
   - Relative slit efficiency -> `andes_cal_rel_eff` -> REL_EFF_<slit>
   - Flux calibration -> `andes_cal_flux` -> ABS_EFF_<slit>
   - Telluric standard -> `andes_cal_telluric_std` -> TELL_MODEL

5. **Science reduction**
   - Science -> `andes_science` (applies all calibrations, drift correction, sky subtraction, flux calibration, telluric correction)
   - RV standards are reduced by `andes_science` via a separate task (`rv_std`); spec v1.2 dropped `andes_cal_RV_std` and `andes_cal_contam`

### Modular Recipe Design

Traditional ESO pipelines have each recipe internally apply detector calibrations (bias subtraction, dark correction, bad pixel masking, etc.) as its first steps. ANDES instead splits these common steps into standalone utility recipes that appear as separate tasks in the EDPS workflow. This means what was traditionally one recipe becomes a chain of two or more, connected via subworkflows.

The three utility recipes are:

- `andes_util_detcal` - applies detector calibrations (bias, dark, gain, bad pixels, linearity, cosmic correction) to any raw frame. Produces a cleaned 2D image. Supports swapped-frame subtraction. The output needs to be classified depending on the input classification (cleaned dark is still a dark, etc.).
- `andes_util_bkgr` - measures and subtracts inter-order scattered light background
- `andes_util_extract` - extracts spectral orders using order definition and slit characterization

These are building blocks that appear multiple times in the workflow with different inputs. Only steps that are large enough and common enough to warrant reuse are split out this way - other recipes remain multi-step internally (e.g. `andes_cal_wave_FP` does line detection, fitting, and solution computation all in one).

#### Examples of recipe chaining

Calibration recipes that traditionally did everything internally now become two-step chains:

```
raw darks  -> detcal(bias)       -> cleaned darks -> cal_dark -> MASTER_DARK
raw flats  -> detcal(bias, dark) -> cleaned flats -> cal_flat -> MASTER_FLAT, BLAZE, ...
raw orderdef -> detcal(bias, dark) -> cleaned frames -> cal_orderdef -> ORDER_TABLE
```

Science reduction becomes a longer chain:

```
raw science -> detcal(bias, dark) -> bkgr -> extract(orderdef, slit, flat) -> science(wave, contam, ...)
```

Each `->` is a task in the EDPS workflow. The detcal step takes different calibration inputs depending on what it's cleaning, and is implemented as a subworkflow.

#### How this maps to EDPS subworkflows

In EDPS, these chains are expressed as `@subworkflow` functions. Each subworkflow groups the full logical chain (detcal + main recipe, or detcal + extract + calibration recipe):

```python
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
```

Longer chains follow the same pattern:

```python
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
```

#### Classification within subworkflows

Within a subworkflow, intermediate products flow directly between tasks via `with_main_input(previous_task)` - no classification lookup happens. The recipe doesn't need to know whether it's cleaning a dark or a flat; the workflow determines what goes in and out.

Classification only matters at boundaries where products need to be found by other tasks via association rules. There, the recipe's output PRO.CATG header determines how EDPS classifies the product.

EDPS has no mechanism to modify output file headers at the task level. Related features:
- `.with_input_map({OLD_TAG: NEW_TAG})` remaps classification tags in the SOF before passing files to the recipe, but does not alter file headers
- `.with_output_filter()` / `.with_input_filter()` select/reject which products pass downstream or reach the recipe

So for generic utility recipes like `andes_util_detcal`: within a subworkflow they can be fully context-unaware. If their products need to be found by association outside a subworkflow, either the recipe propagates appropriate headers, or the consuming task uses `.with_input_map()` to re-tag at the SOF level.

### Data Classification Keywords

Files are classified by FITS headers (resolved naming, see andes_classification.py):
- `instrume`: "ANDES"
- `dpr.catg`: "CALIB", "SCIENCE" or "TECHNICAL" (LED flats)
- `dpr.type`: `<KIND>,<A>,<B>` for echelle calibrations (KIND one of ORDERDEF, SLITMASK, FLAT, WAVE, STD; sources one of LAMP, OFF, FP, LFC, HCL, SKY, FLUX, RV, TELLURIC), plain `<A>,<B>` for science (e.g. "OBJECT,SKY", "OBJECT,WAVE" in TC mode), single-slot for IFU (e.g. "FLAT,LAMP", "OBJECT")
- `dpr.tech`: "IMAGE", "ECHELLE,FIBER" or "ECHELLE,IFU", optionally with a third element (SWAPPING/OFFSET/DITHERING)
- `seq.arm`: spectrograph (UBV, RIZ, YJH, K); `ins.mode`: SL-UNI or IFU-AO; `det.binx`/`det.biny`: binning
- `ins.calfib`: calibration fibre (C) source, FP/HCL/LFC/LAMP/OFF (dedicated keyword per Templates Manual and ESO-044156; name pending ICD; informational, not used in classification)

Sub-slit order in comma-separated values is A, B (Templates Manual E-AND-SW-MAN-06-00-001 v2.0; the calibration fibre C is not part of DPR.TYPE, see `ins.calfib`). The spectrograph is NOT encoded in dpr.tech; grouping/matching runs over the setup keywords, so one task graph serves all arms, binnings and modes. There is a 1:1 correspondence between raw DPR.TYPE kinds, templates and recipes.

Products carry per-slit PRO.CATG suffixes `_A`, `_B`, `_C` or `_IFU`. Products with the same role from different recipes get origin prefixes to keep PRO.CATG unambiguous (S1D_WAVE_*, S1D_STD_FLUX_*, S1D_STD_TELL_*; bare S1D_*/SS1D_* are science products).

### Testing

```bash
uv run pytest                                          # classification + task-graph tests
uv run python tests/make_test_data.py <dir> [--arms RIZ,YJH]   # synthetic raw data, plan-driven
uv run edps -w andes.andes_wkf -i <dir> -c             # classify
uv run edps -w andes.andes_wkf -i <dir> -od            # organize (jobs + associations, no execution)
PYESOREX_PLUGIN_DIR=$PWD/recipes uv run edps -w andes.andes_wkf -i <dir> -t science   # full run with dummy recipes
# NB: the env vars must reach the EDPS *server*: if one is already running
# without them (or with a foreign ESOREX_PLUGIN_DIR from another pipeline
# kit), every job fails in pyesorex get_c_recipes -- `edps -shutdown` first.
```

`tests/make_test_data.py` is **plan-driven**: it walks `calibration_plan.yaml`
(the same file `andes-sim night` consumes) and writes header-only frames, so the
DPR grammar has a single source and cannot drift from the classification rules.
It self-checks every frame against the workflow's own rules and prints a coverage
report. Planned types the workflow can't classify yet (reconciliation 1/2/4:
`FLAT,LAMP,LAMP`, `WAVE,FP,OFF`, `FLAT,OFF,OFF`, …) show up as UNCLASSIFIED —
surfaced, not hidden. On the two features that aren't officially part of the
instrument yet: (1) no fibre mask (M1/M2/M3) — but `SLIT_CURVE` is measured from
FP lines across a fully-illuminated pseudo-slit and doesn't need the mask, so
IFU still gets a slit characterization from a plain FP exposure (`SLITMASK,FP`,
plan procedure C-slit-IFU); `slit_curve` therefore stays a required association
(`min_ret=1`) in both modes. (2) No LFC — `wave_lfc` is an alternative to
`wave_fp`, so a night with no LFC just resolves via FP. A plan-driven night
organizes to 98 complete jobs (RIZ SL, YJH SL, YJH IFU).

`recipes/andes_cal_bias.py` is the first real recipe (the template for the others: MEF products mirroring the raw layout, per-extension QC, closed-loop validated against simulator truth). `recipes/andes_dummy_recipes.py` provides dummy implementations of the remaining recipes; they write empty FITS products with the correct PRO.CATG and inherit setup keywords, so the whole cascade executes end-to-end.

### Current State

Full workflow per spec E-AND-SW-SPE-09-00-002 v1.2: all 16 recipes as tasks/subworkflows (bias, dark, led, orderdef, slit, lsf, flat, wave_fp, wave_lfc, rel_eff, flux, telluric, science, rv_std + detcal/bkgr/extract steps). Wave FP/LFC are alternatives (FP preferred). Detector calibrations are optional associations (min_ret=0) since their availability is arm-dependent (no bias for NIR). Static tables (HCL_LINES_TABLE, STD_STAR_TABLE, STD_TELL_TABLE) are matched on instrume+seq.arm. DPR grammar follows the Templates Manual v2.0 (two slots A,B; calibration fibre in `ins.calfib`; SLITMASK instead of SLIT; sky flats FLAT,SKY,SKY; no LSF raw type - the LSF task consumes SLITMASK frames). Deltas against the DRL spec and AD2 are tracked in `calibration_plan.yaml` under `reconciliation` (item 10 = the grammar decision).
