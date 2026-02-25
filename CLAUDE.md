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
    andes_wkf.py          # Main workflow definition (tasks, data sources, classification rules)
  recipes/                # Directory for pyesorex recipe plugins (set via .env)
  docs/                   # EDPS documentation PDFs
  pyproject.toml          # uv project config
  .env                    # Sets PYESOREX_PLUGIN_DIR=./recipes
```

All commands use `uv run`, e.g. `uv run edps -lw` or `uv run pyesorex`.

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

Currently, `andes_wkf.py` contains everything in one file. As the workflow grows it should be split per the convention above.

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
   - BIAS (VIS only) -> `andes_cal_bias` -> MASTER_BIAS
   - DARK (VIS & NIR) -> `andes_cal_dark` -> MASTER_DARK, HOT_PIXEL_MASK
   - LED flat-field / gain (VIS) -> `andes_cal_led` -> BAD_PIXEL_MASK, GAIN
   - Linearity (NIR) -> `andes_cal_lin` -> LINEARITY_COEFFICIENTS
   - Detector calibration utility -> `andes_util_detcal` (applies bias, dark, gain, bad pixels, linearity to any raw frame)

2. **Geometric calibration**
   - Order definition -> `andes_cal_orderdef` -> ORDER_TABLE
   - Slit characterization -> `andes_cal_slit` -> SLIT_MODEL (tilt, curvature from FP/LFC lines)

3. **Spectroscopic calibration**
   - Flat-field, blaze, order profile -> `andes_cal_flat` -> MASTER_FLAT, BLAZE, ORDER_PROFILE
   - LSF characterization -> `andes_cal_LSF` -> LSF_MODEL
   - Wavelength calibration (FP) -> `andes_cal_wave_FP` -> WAVE_SOLUTION
   - Wavelength calibration (LFC) -> `andes_cal_wave_LFC` -> WAVE_SOLUTION (alternative)
   - Background subtraction -> `andes_util_bkgr` (inter-order scattered light)
   - Extraction -> `andes_util_extract` (uses ORDER_TABLE, SLIT_MODEL, FLAT, BLAZE)

4. **Cross-calibration**
   - Contamination measurement -> `andes_cal_contam` -> CONTAM_FRAME
   - Relative slit efficiency -> `andes_cal_rel_eff` -> REL_EFF_CURVE
   - Flux calibration -> `andes_cal_flux` -> EFFICIENCY_CURVE

5. **Science reduction**
   - Science -> `andes_science` (applies all calibrations, extracts spectra, drift correction, sky subtraction, flux calibration, telluric correction)

6. **Additional calibrations**
   - RV standard -> `andes_cal_RV_std`
   - Telluric standard -> `andes_cal_telluric_std`

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

Files are classified by FITS headers:
- `instrume`: "ANDES"
- `dpr.catg`: "CALIB" or "SCIENCE"
- `dpr.type`: identifies the frame type (e.g. "BIAS", "DARK", "FLAT,FLAT,FLAT", "OBJECT,FP,SKY")
- `dpr.tech`: identifies the technique/mode (e.g. "IMAGE,RIZ", "ECHELLE,RIZ")

The `dpr.type` values are comma-separated when describing what's in each sub-slit (A, C, B). E.g. "OBJECT,FP,SKY" means object in A, FP calibration in C, sky in B.

### Current State

The `andes_wkf.py` implements RIZ-only subworkflows for dark, flat, wavecal, and science reduction, using the modular detcal/extract/bkgr pattern. Classification rules and data sources are simplified (match on `instrume` only). To be extended with orderdef, slit characterization, additional spectrographs, and refined classification/association rules.
