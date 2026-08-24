# ANDES EDPS project tasks.
#
# `edps` needs PYESOREX_PLUGIN_DIR pointed at ./recipes AND any foreign
# ESOREX_PLUGIN_DIR removed from the environment (~/.zshrc exports one for
# other ESO pipeline kits); otherwise the EDPS server the first client call
# spawns fails every job in pyesorex get_c_recipes. `.env` cannot fix this --
# uv does not override an already-set variable -- so the correct environment
# is injected here instead. If a server is already running with the wrong
# environment, `just shutdown` first.

recipes := justfile_directory() / "recipes"
edps_env := "env -u ESOREX_PLUGIN_DIR PYESOREX_PLUGIN_DIR=" + recipes

# run the edps client with the correct plugin environment (pass any args)
edps *args:
    {{edps_env}} uv run edps {{args}}

# restart the edps server (do this after workflow changes)
shutdown:
    -{{edps_env}} uv run edps -shutdown

# pytest suite
test *args:
    uv run pytest {{args}}

# generate a plan-driven headers-only night
testdata dir arms="RIZ,YJH":
    uv run python tests/make_test_data.py "{{dir}}" --arms "{{arms}}"

# regenerate the workflow graph PNGs (collapsed + detailed)
graph:
    {{edps_env}} uv run edps -w andes.andes_wkf -g 2>/dev/null | dot -Tpng > andes.png
    {{edps_env}} uv run edps -w andes.andes_wkf -g2 2>/dev/null | dot -Tpng > andes_detailed.png
