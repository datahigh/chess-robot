#!/usr/bin/env python3
"""Generate config/board_coordinates.yaml: world (x,y) of every square centre
(a1..h8) and graveyard slot (GY1..GY16), in metres, from config/arm_params.yaml.

Convention (see arm_params.yaml): board centre = world origin, surface z=0,
files a..h along +X, ranks 1..8 along +Y. Square centre = (i-3.5)*square.

    python3 scripts/gen_board_coordinates.py
"""
import os
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(HERE, os.pardir, "config")
FILES = "abcdefgh"


def main():
    with open(os.path.join(CFG, "arm_params.yaml")) as f:
        p = yaml.safe_load(f)

    sq = p["board"]["square_size_mm"] / 1000.0
    gv = p["graveyard"]
    rows = [x / 1000.0 for x in gv["rows_x_mm"]]
    col0 = gv["col0_y_mm"] / 1000.0
    pitch = gv["pitch_mm"] / 1000.0

    squares = {}
    for fi in range(8):
        for ri in range(8):
            name = f"{FILES[fi]}{ri + 1}"
            squares[name] = {"x": round((fi - 3.5) * sq, 6),
                             "y": round((ri - 3.5) * sq, 6)}

    graveyard = {}
    n = 0
    for rx in rows:
        for c in range(8):
            n += 1
            graveyard[f"GY{n}"] = {"x": round(rx, 6),
                                   "y": round(col0 + c * pitch, 6)}

    out = {
        "_generated_by": "gen_board_coordinates.py - DO NOT EDIT BY HAND",
        "units": "m",
        "surface_z": p["board"]["surface_z_mm"] / 1000.0,
        "grasp_z": p["task_heights_mm"]["grasp_z"] / 1000.0,
        "lift_z": p["task_heights_mm"]["lift_z"] / 1000.0,
        "squares": squares,
        "graveyard": graveyard,
    }

    dest = os.path.join(CFG, "board_coordinates.yaml")
    with open(dest, "w") as f:
        yaml.safe_dump(out, f, sort_keys=False, default_flow_style=False,
                       allow_unicode=True)
    print(f"Wrote {len(squares)} squares + {len(graveyard)} graveyard slots -> {dest}")


if __name__ == "__main__":
    main()
