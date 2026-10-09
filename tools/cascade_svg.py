"""Draw the ANDES workflow as a reduction-cascade bus diagram (DRL spec Fig 10 style).

Reads the task graph straight from the EDPS workflow module, so the picture
cannot drift from the code:

    uv run python tools/cascade_svg.py [andes.andes_wkf] -o andes_cascade.svg

Columns are task chains (one subworkflow, or a lone task). Every product set
consumed outside its own chain becomes a horizontal bus starting at its
producer; each consuming task has its own rail on the left of its column and
taps the buses it uses with a dot. Products nobody consumes are listed at the
bottom, taken from the dummy recipes' output table.
"""

import argparse
import importlib
import re
import sys
import warnings
from html import escape
from pathlib import Path

warnings.filterwarnings("ignore")

from edps.generator.task import DataSource, Task  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

FONT = "DejaVu Sans Mono, Menlo, Consolas, monospace"
FS = 11
CW = 6.65  # monospace advance at FS
BOX_H = 34
RAIL_STEP = 7
ROW_GAP = 16
BUS_GAP = 10
LINE_H = 13
COL_GAP = 22

# assigned to producers in column order; neighbours in the cascade get distinct hues
BUS_COLORS = ["#4e79a7", "#e15759", "#2a9d8f", "#59a14f", "#b07aa1", "#f28e2b",
              "#9c755f", "#263238", "#7f3c8d", "#3969ac", "#e73f74", "#80ba5a",
              "#8c564b", "#17becf"]

SLIT = re.compile(r"_(A|B|C|IFU)$")


def collapse(cats):
    out = []
    for c in cats:
        c = SLIT.sub("_*", c)
        if c not in out:
            out.append(c)
    return out


def text_w(s):
    return len(s) * CW


# --- graph extraction -------------------------------------------------------

def load(module_name):
    sys.path.insert(0, str(ROOT))
    wkf = importlib.import_module(module_name)
    tasks = {}

    def walk(t):
        if isinstance(t, Task) and t.name not in tasks:
            tasks[t.name] = t
            walk(t.main_input)
            for g in t.associated_input_groups:
                for a in g.associated_inputs:
                    walk(a.input_task)

    chain_order = []
    for v in vars(wkf).values():
        if isinstance(v, Task):
            walk(v)
            key = chain_key(v)
            if key not in chain_order:
                chain_order.append(key)
    for t in tasks.values():
        if chain_key(t) not in chain_order:
            chain_order.append(chain_key(t))

    chains = {}
    for key in chain_order:
        members = [t for t in tasks.values() if chain_key(t) == key]
        # order along the main-input links
        ordered = [t for t in members if not isinstance(t.main_input, Task)
                   or chain_key(t.main_input) != key]
        while len(ordered) < len(members):
            nxt = [t for t in members if t not in ordered and t.main_input is ordered[-1]]
            ordered.append(nxt[0] if nxt else next(t for t in members if t not in ordered))
        chains[key] = ordered
    return module_name, chains


def chain_key(t):
    return t.subworkflow_name[0] if t.subworkflow_name else t.name


def levels(chains):
    memo = {}

    def lev(t):
        if not isinstance(t, Task):
            return -1
        if t.name not in memo:
            inputs = [t.main_input] + [a.input_task for g in t.associated_input_groups
                                       for a in g.associated_inputs]
            memo[t.name] = 1 + max(lev(i) for i in inputs)
        return memo[t.name]

    for ts in chains.values():
        for t in ts:
            lev(t)
    return memo


def analyse(chains):
    """Buses, in-chain side inputs and static inputs."""
    by_producer = {}   # producer -> {cat: {consumer: (min_ret, alt_rank)}}
    side = []          # (source task, target task) inside one chain
    statics = {}       # consumer -> [(name, min_ret)]
    for key, ts in chains.items():
        for t in ts:
            for g in t.associated_input_groups:
                alt = len(g.associated_inputs) > 1
                for rank, a in enumerate(g.associated_inputs, 1):
                    src = a.input_task
                    if isinstance(src, DataSource):
                        statics.setdefault(t.name, []).append((src.name, a.min_ret))
                    elif chain_key(src) == key:
                        side.append((src.name, t.name))
                    else:
                        cats = collapse(sorted(a.categories)) or ["(all products)"]
                        slot = by_producer.setdefault(src.name, {})
                        for c in cats:
                            slot.setdefault(c, {})[t.name] = (a.min_ret, rank if alt else None)
    buses = []
    for prod, cats in by_producer.items():
        groups = {}
        for c, cons in cats.items():
            groups.setdefault(tuple(sorted(cons.items())), []).append(c)
        for cons, cs in groups.items():
            buses.append({"producer": prod, "cats": cs, "consumers": dict(cons)})
    return buses, side, statics


def leftover_products(chains, buses):
    """Products of each chain's final recipe that no other task consumes."""
    sys.path.insert(0, str(ROOT / "recipes"))
    try:
        from andes_dummy_recipes import RECIPES
    except Exception:
        return {}
    consumed = {}
    for b in buses:
        consumed.setdefault(b["producer"], set()).update(b["cats"])
    out = {}
    for ts in chains.values():
        t = ts[-1]
        if t.command in RECIPES:
            cats = collapse(RECIPES[t.command]("X", ["A", "B", "C", "IFU"]))
            rest = [c for c in cats if c not in consumed.get(t.name, set())]
            if rest:
                out[t.name] = rest
    return out


# --- layout + drawing ---------------------------------------------------------

def short(cmd):
    return cmd.removeprefix("andes_")


def meta_label(t):
    m = {x.lower() for x in t.meta_targets}
    tags = [lbl for key, lbl in (("science", "SCIENCE"), ("qc1calib", "QC1"),
                                 ("calchecker", "CALCHECKER")) if key in m]
    return " · ".join(tags)


def render(title, chains, out_path):
    lev = levels(chains)
    buses, side, statics = analyse(chains)
    leftovers = leftover_products(chains, buses)
    task_by_name = {t.name: t for ts in chains.values() for t in ts}
    chain_of = {t.name: k for k, ts in chains.items() for t in ts}
    index_in_chain = {t.name: i for ts in chains.values() for i, t in enumerate(ts)}

    col_of_chain = {k: i for i, k in enumerate(chains)}
    for b in buses:
        b["col"] = col_of_chain[chain_of[b["producer"]]]
    producers = []
    for b in sorted(buses, key=lambda b: b["col"]):
        if b["producer"] not in producers:
            producers.append(b["producer"])
    pcolor = {p: BUS_COLORS[i % len(BUS_COLORS)] for i, p in enumerate(producers)}

    # columns
    cols = []
    x = 24
    for key, ts in chains.items():
        bw = max(max(text_w(t.main_input.name), text_w(short(t.command))) for t in ts) + 18
        bw = max(bw, text_w(key) + 18, 118)
        left_pad = 12 + RAIL_STEP * (len(ts) - 1) + 4
        tag_w = max((text_w(n) + 22 for t in ts for n, _ in statics.get(t.name, [])), default=0)
        right_pad = 14 + (tag_w + 8 if tag_w else 0)
        box_left = x + left_pad
        cols.append({"key": key, "x0": x, "box_left": box_left, "bw": bw,
                     "x1": box_left + bw + right_pad})
        x = box_left + bw + right_pad + COL_GAP
    width = x + 10
    col_by_key = {c["key"]: c for c in cols}

    def rail_x(tname):
        c = col_by_key[chain_of[tname]]
        return c["box_left"] - 12 - RAIL_STEP * index_in_chain[tname]

    # rows: tasks of one level, then the buses those tasks produce
    y = 104
    box_y = {}
    max_level = max(lev.values())
    for L in range(max_level + 1):
        row = [n for n, l in lev.items() if l == L]
        for n in row:
            box_y[n] = y
        y += BOX_H + ROW_GAP
        for b in sorted((b for b in buses if lev[b["producer"]] == L), key=lambda b: b["col"]):
            h = LINE_H * len(b["cats"]) + 8
            b["y"] = y
            b["h"] = h
            b["cy"] = y + h / 2
            y += h + BUS_GAP
        y += ROW_GAP - BUS_GAP
    bottom_y = y + 16
    bottom_h = max((LINE_H * len(v) + 8 for v in leftovers.values()), default=0)
    legend_y = bottom_y + bottom_h + 40
    height = legend_y + 70

    s = []
    a = s.append
    a(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" '
      f'viewBox="0 0 {width:.0f} {height:.0f}" font-family="{FONT}" font-size="{FS}">')
    a('<defs>'
      '<marker id="ah" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" '
      'orient="auto-start-reverse"><path d="M0,0 L8,4 L0,8 z" fill="#555"/></marker>'
      '</defs>')
    a(f'<rect width="100%" height="100%" fill="#ffffff"/>')
    a(f'<text x="24" y="34" font-size="18" font-weight="bold" fill="#222">'
      f'{escape(title)} — reduction cascade</text>')
    a(f'<text x="24" y="54" fill="#666">generated from the EDPS task graph by '
      f'tools/cascade_svg.py · columns are task chains (subworkflows), '
      f'buses are products consumed outside their chain</text>')

    # column headers + faint guides down to the first box
    for c in cols:
        ts = chains[c["key"]]
        cx = c["box_left"] + c["bw"] / 2
        a(f'<text x="{cx:.1f}" y="82" text-anchor="middle" font-weight="bold" '
          f'font-size="12" fill="#222">{escape(c["key"])}</text>')
        a(f'<text x="{cx:.1f}" y="95" text-anchor="middle" font-size="8.5" '
          f'fill="#888">{escape(meta_label(ts[-1]))}</text>')

    # chain spines
    for key, ts in chains.items():
        c = col_by_key[key]
        cx = c["box_left"] + c["bw"] / 2
        for prev, nxt in zip(ts, ts[1:]):
            a(f'<line x1="{cx:.1f}" y1="{box_y[prev.name] + BOX_H}" x2="{cx:.1f}" '
              f'y2="{box_y[nxt.name] - 1}" stroke="#555" stroke-width="1.3" marker-end="url(#ah)"/>')

    # producer spines to their product boxes, and to the leftover box
    for p in producers:
        c = col_by_key[chain_of[p]]
        cx = c["box_left"] + c["bw"] / 2
        last = max(b["y"] for b in buses if b["producer"] == p)
        a(f'<line x1="{cx:.1f}" y1="{box_y[p] + BOX_H}" x2="{cx:.1f}" y2="{last}" '
          f'stroke="{pcolor[p]}" stroke-width="1.6"/>')
    for p in leftovers:
        c = col_by_key[chain_of[p]]
        cx = c["box_left"] + c["bw"] / 2
        a(f'<line x1="{cx:.1f}" y1="{box_y[p] + BOX_H}" x2="{cx:.1f}" y2="{bottom_y}" '
          f'stroke="#bbb" stroke-width="1" stroke-dasharray="2 3"/>')

    # buses
    for b in buses:
        c = col_by_key[chain_of[b["producer"]]]
        x0 = c["box_left"]
        bw = max(text_w(t) for t in b["cats"]) + 14
        x_end = max(rail_x(t) for t in b["consumers"]) + 10
        col = pcolor[b["producer"]]
        a(f'<line x1="{x0 + bw:.1f}" y1="{b["cy"]:.1f}" x2="{x_end:.1f}" y2="{b["cy"]:.1f}" '
          f'stroke="{col}" stroke-width="1.8"/>')
        a(f'<rect x="{x0:.1f}" y="{b["y"]:.1f}" width="{bw:.1f}" height="{b["h"]:.1f}" rx="2" '
          f'fill="#fbd65a" stroke="#b8901a" stroke-width="1"/>')
        a(f'<rect x="{x0:.1f}" y="{b["y"]:.1f}" width="4" height="{b["h"]:.1f}" fill="{col}"/>')
        for i, t in enumerate(b["cats"]):
            a(f'<text x="{x0 + 9:.1f}" y="{b["y"] + 14 + i * LINE_H:.1f}" fill="#3a2e00">'
              f'{escape(t)}</text>')

    # rails and taps
    for tname, t in task_by_name.items():
        taps = [(b, b["consumers"][tname]) for b in buses if tname in b["consumers"]]
        if not taps:
            continue
        rx = rail_x(tname)
        top = min(b["cy"] for b, _ in taps)
        ym = box_y[tname] + BOX_H / 2
        box_left = col_by_key[chain_of[tname]]["box_left"]
        a(f'<path d="M{rx:.1f},{top:.1f} V{ym:.1f} H{box_left - 1:.1f}" fill="none" '
          f'stroke="#777" stroke-width="1.2" marker-end="url(#ah)"/>')
        for b, (min_ret, rank) in taps:
            col = pcolor[b["producer"]]
            fill = col if min_ret > 0 else "#fff"
            a(f'<circle cx="{rx:.1f}" cy="{b["cy"]:.1f}" r="3.6" fill="{fill}" '
              f'stroke="{col}" stroke-width="1.6"/>')
            if rank:
                a(f'<text x="{rx + 4:.1f}" y="{b["cy"] - 4:.1f}" font-size="8" '
                  f'font-weight="bold" fill="{col}">{rank}</text>')

    # in-chain side inputs: bracket on the right of the column
    for src, dst in side:
        c = col_by_key[chain_of[dst]]
        xr = c["box_left"] + c["bw"]
        y1 = box_y[src] + BOX_H / 2
        y2 = box_y[dst] + 9
        a(f'<path d="M{xr:.1f},{y1:.1f} H{xr + 9:.1f} V{y2:.1f} H{xr + 1:.1f}" fill="none" '
          f'stroke="#777" stroke-width="1.2" stroke-dasharray="4 2" marker-end="url(#ah)"/>')

    # task boxes
    for tname, t in task_by_name.items():
        c = col_by_key[chain_of[tname]]
        ts = chains[chain_of[tname]]
        final = t is ts[-1]
        m = {x.lower() for x in t.meta_targets}
        if not final:
            fill, stroke = "#eef4fb", "#9db7d5"
        elif "science" in m:
            fill, stroke = "#fde2c4", "#d2904e"
        else:
            fill, stroke = "#cfe2f6", "#4a7bb7"
        dash = ' stroke-dasharray="5 3"' if final and "calchecker" not in m else ""
        bx, by = c["box_left"], box_y[tname]
        raw = not isinstance(t.main_input, Task)
        a(f'<g><title>task {escape(tname)}: {escape(t.main_input.name)} → '
          f'{escape(t.command)}</title>')
        a(f'<rect x="{bx:.1f}" y="{by}" width="{c["bw"]:.1f}" height="{BOX_H}" rx="3" '
          f'fill="{fill}" stroke="{stroke}" stroke-width="1.2"{dash}/>')
        a(f'<text x="{bx + c["bw"] / 2:.1f}" y="{by + 14}" text-anchor="middle" '
          f'fill="#1a1a1a"{" font-weight=\"bold\"" if raw else ""}>{escape(t.main_input.name)}</text>')
        a(f'<text x="{bx + c["bw"] / 2:.1f}" y="{by + 27}" text-anchor="middle" '
          f'fill="#4a5a70">{escape(short(t.command))}</text></g>')

        # static calibration tables, tagged on the right
        for i, (name, min_ret) in enumerate(statics.get(tname, [])):
            tx = bx + c["bw"] + 18
            ty = by + BOX_H - 15 + i * 18
            tw = text_w(name) + 14
            a(f'<line x1="{tx:.1f}" y1="{ty + 7:.1f}" x2="{bx + c["bw"] + 1:.1f}" y2="{ty + 7:.1f}" '
              f'stroke="#8a78c0" stroke-width="1.2"{"" if min_ret else " stroke-dasharray=\"3 2\""} '
              f'marker-end="url(#ah)"/>')
            a(f'<path d="M{tx:.1f},{ty:.1f} h{tw - 6:.1f} l6,6 v8 h{-tw:.1f} z" '
              f'fill="#ece7f8" stroke="#8a78c0" stroke-width="1"/>')
            a(f'<text x="{tx + 6:.1f}" y="{ty + 11:.1f}" font-size="9.5" fill="#3d2f6b">'
              f'{escape(name)}</text>')

    # products nobody consumes
    for p, cats in leftovers.items():
        c = col_by_key[chain_of[p]]
        bw = max(text_w(t) for t in cats) + 14
        h = LINE_H * len(cats) + 8
        sci = "science" in {x.lower() for x in task_by_name[p].meta_targets}
        fill, stroke = ("#fbd65a", "#b8901a") if sci else ("#fdf3cf", "#d9c27a")
        a(f'<rect x="{c["box_left"]:.1f}" y="{bottom_y}" width="{bw:.1f}" height="{h}" rx="2" '
          f'fill="{fill}" stroke="{stroke}"/>')
        for i, t in enumerate(cats):
            a(f'<text x="{c["box_left"] + 7:.1f}" y="{bottom_y + 14 + i * LINE_H}" '
              f'fill="#3a2e00">{escape(t)}</text>')

    # legend
    lx, ly = 24, legend_y
    items = [
        ("dot", "#4e79a7", "required input (min_ret ≥ 1)"),
        ("hollow", "#4e79a7", "optional input (min_ret = 0)"),
        ("alt", "#4e79a7", "alternative input, preference order"),
        ("side", None, "input from an earlier step of the same chain"),
        ("static", None, "static calibration table"),
        ("dashbox", None, "not a CALCHECKER target"),
    ]
    a(f'<text x="{lx}" y="{ly - 14}" fill="#666">'
      f'boxes: main input (top) · recipe (bottom) · products: * = per slit (A, B, C or IFU) · '
      f'bottom row: products not consumed by any task</text>')
    for i, (kind, col, label) in enumerate(items):
        ix = lx + (i % 3) * 360
        iy = ly + 6 + (i // 3) * 22
        if kind in ("dot", "hollow", "alt"):
            a(f'<line x1="{ix}" y1="{iy}" x2="{ix + 30}" y2="{iy}" stroke="{col}" stroke-width="1.8"/>')
            a(f'<circle cx="{ix + 15}" cy="{iy}" r="3.6" fill="{col if kind != "hollow" else "#fff"}" '
              f'stroke="{col}" stroke-width="1.6"/>')
            if kind == "alt":
                a(f'<text x="{ix + 19}" y="{iy - 4}" font-size="8" font-weight="bold" fill="{col}">1</text>')
        elif kind == "side":
            a(f'<path d="M{ix},{iy - 6} h10 v12 h-8" fill="none" stroke="#777" stroke-width="1.2" '
              f'stroke-dasharray="4 2" marker-end="url(#ah)"/>')
        elif kind == "static":
            a(f'<path d="M{ix},{iy - 7} h24 l6,6 v8 h-30 z" fill="#ece7f8" stroke="#8a78c0"/>')
        elif kind == "dashbox":
            a(f'<rect x="{ix}" y="{iy - 8}" width="30" height="16" rx="3" fill="#cfe2f6" '
              f'stroke="#4a7bb7" stroke-dasharray="5 3"/>')
        a(f'<text x="{ix + 40}" y="{iy + 4}" fill="#333">{escape(label)}</text>')

    a('</svg>')
    Path(out_path).write_text("\n".join(s))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("module", nargs="?", default="andes.andes_wkf")
    ap.add_argument("-o", "--output", default="andes_cascade.svg")
    args = ap.parse_args()
    title, chains = load(args.module)
    render(title, chains, args.output)
    print(args.output)


if __name__ == "__main__":
    main()
