"""Structural checks of the task graph: completeness, uniqueness, wiring."""

from edps.generator.task import DataSource, Task

from andes import andes_datasources as ds
from andes import andes_wkf as wkf


def walk(node, tasks, sources):
    if isinstance(node, DataSource):
        sources.add(node)
        return
    if node in tasks:
        return
    tasks.add(node)
    walk(node.main_input, tasks, sources)
    for group in node.associated_input_groups:
        for assoc in group.associated_inputs:
            walk(assoc.input_task, tasks, sources)


def graph():
    tasks, sources = set(), set()
    for final in (wkf.science_task, wkf.rv_std_task):
        walk(final, tasks, sources)
    return tasks, sources


def test_all_tasks_reachable_from_science_and_rv():
    tasks, _ = graph()
    expected = {
        "bias",
        "dark_detcal", "dark",
        "led_detcal", "led",
        "orderdef_detcal", "orderdef",
        "slit_detcal", "slit",
        "flat_detcal", "flat_extract", "flat",
        "lsf_detcal", "lsf",
        "wave_fp_detcal", "wave_fp_extract", "wave_fp",
        "wave_lfc_detcal", "wave_lfc_extract", "wave_lfc",
        "eff_detcal", "eff_extract", "rel_eff",
        "flux_detcal", "flux_bkgr", "flux_extract", "flux",
        "telluric_detcal", "telluric_bkgr", "telluric_extract", "telluric",
        "science_detcal", "science_bkgr", "science_extract", "science",
        "rv_std_detcal", "rv_std_bkgr", "rv_std_extract", "rv_std",
    }
    assert {t.name for t in tasks} == expected


def test_task_names_unique():
    tasks, _ = graph()
    names = sorted(t.name for t in tasks)
    assert len(names) == len(set(names))


def test_every_data_source_is_consumed():
    _, used = graph()
    defined = {v for v in vars(ds).values() if isinstance(v, DataSource)}
    assert defined == used


def test_final_tasks():
    assert isinstance(wkf.science_task, Task)
    assert "science" in wkf.science_task.meta_targets
    assert "qc1calib" in wkf.rv_std_task.meta_targets
    assert "science" not in wkf.rv_std_task.meta_targets
    assert wkf.science_task.command == "andes_science"
    assert wkf.rv_std_task.command == "andes_science"


def test_recipes_match_specification():
    tasks, _ = graph()
    recipes = {t.command for t in tasks}
    assert recipes == {
        "andes_util_detcal", "andes_util_bkgr", "andes_util_extract",
        "andes_cal_bias", "andes_cal_dark", "andes_cal_led",
        "andes_cal_orderdef", "andes_cal_slit", "andes_cal_LSF",
        "andes_cal_flat", "andes_cal_wave_FP", "andes_cal_wave_LFC",
        "andes_cal_rel_eff", "andes_cal_flux", "andes_cal_telluric_std",
        "andes_science",
    }


def test_science_chain_order():
    extract = wkf.science_task.main_input
    bkgr = extract.main_input
    detcal = bkgr.main_input
    assert [extract.command, bkgr.command, detcal.command] == [
        "andes_util_extract", "andes_util_bkgr", "andes_util_detcal"]
    assert detcal.main_input is ds.science


def test_wave_alternatives_prefer_fp():
    groups = [g for g in wkf.science_task.associated_input_groups
              if len(g.associated_inputs) == 2]
    assert len(groups) == 1
    names = [a.input_task.name for a in groups[0].associated_inputs]
    assert names == ["wave_fp", "wave_lfc"]
