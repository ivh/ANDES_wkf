# ANDES EDPS Workflow

EDPS data-reduction workflow and pyesorex recipes for **ANDES**, the
high-resolution echelle spectrograph for ESO's ELT. The workflow classifies
raw frames, associates calibrations and runs the reduction cascade across all
four spectrographs, both observing modes (SL-UNI, IFU-AO) and all binnings
from one generic task graph.

See [CLAUDE.md](CLAUDE.md) for the full design and conventions,
[wkf_status.md](wkf_status.md) for the progress log, and [docs/](docs/) for
the EDPS reference PDFs and project notes.

## Setup

```bash
uv sync            # pulls pyesorex + cpl from the ESO / pycpl indexes
```

All commands run under `uv`. Drive the EDPS client through the **justfile**
(`just edps ...`), which injects `PYESOREX_PLUGIN_DIR` and strips any foreign
`ESOREX_PLUGIN_DIR` inherited from the shell — without that the EDPS server
fails every job in `pyesorex get_c_recipes`.

## Common tasks

```bash
just test                                             # pytest suite
just testdata <dir>                                   # plan-driven headers-only test night
just pyesorex --recipes                               # list installed recipe plugins
just edps -w andes.andes_wkf -lw                      # list workflows
just edps -w andes.andes_wkf -lt                      # list tasks / meta-targets
just edps -w andes.andes_wkf -i <dir> -c              # classify raw frames
just edps -w andes.andes_wkf -i <dir> -od             # organize (jobs + associations, no run)
just edps -w andes.andes_wkf -i <dir> -t science rv_std   # full run (dummy + real recipes)
just graph                                            # regenerate andes.png + andes_detailed.png
just shutdown                                          # restart the server after workflow changes
```

Multiple targets go in one flag: `-t science rv_std` (a second `-t` overrides,
it does not append). After changing recipes or the workflow, `just shutdown`
so the next client call respawns the server with a fresh environment.

## Test data

`just testdata <dir>` writes a header-only synthetic night derived from
[`calibration_plan.yaml`](calibration_plan.yaml) — the canonical plan the E2E
simulator also consumes — so the DPR grammar has a single source. It
self-checks every frame against the workflow's classification rules and prints
a coverage report. A plan-driven night organizes to 98 complete jobs
(RIZ SL, YJH SL, YJH IFU).

**Real-pixel** raw frames come from the E2E simulator instead
(`~/ANDES/E2E/src`): `uv run andes-sim night calibration_plan.yaml ...`.
The detector-recipe tests grow a closed-loop check against a real simulator
frame when `$ANDES_RAWNIGHTS` (default `~/ANDES/E2E/rawnights`) is present,
and skip otherwise.

## Recipes

pyesorex recipe plugins live in [recipes/](recipes/). `andes_cal_bias` and
`andes_util_detcal` are real; the rest are dummy stand-ins that write empty
products with the correct `PRO.CATG`, so the whole cascade executes
end-to-end while recipes are filled in one by one.
