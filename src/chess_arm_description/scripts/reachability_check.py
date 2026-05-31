#!/usr/bin/env python3
"""Phase-0 reachability proof for the 6-DOF chess arm.

Reads the canonical parameters from config/arm_params.yaml (the single source of
truth for software), ASSERTS they agree with urdf/arm_params.xacro (the URDF
source) so the two cannot drift, then verifies that every one of the 64 squares
plus all 16 graveyard slots is reachable for a TOP-DOWN grasp at both the grasp
and lift heights, with margin.

Model (matches the kinematic design):
  - World origin at board centre; board surface z=0; Z up.
  - J1 yaw aims the arm plane at the target.
  - J2 shoulder-pitch + J3 elbow-pitch form a 2-link planar arm (upper_arm, forearm).
  - J4/J5/J6 spherical wrist intersects at the WRIST CENTRE (J5).
  - Tool points straight down, so the grasp point is tool_offset = wrist + tool_tip
    BELOW the wrist centre: WC = (tx, ty, tz + tool_offset).
  - Reachable iff WC_z>0, the planar shoulder->WC distance D is inside the annulus
    [|UA-FA|+20, UA+FA-30] mm, J1 yaw within limits, and the elbow-up 2-link IK
    keeps J2/J3 within limits. margin = (UA+FA) - D.

Exit code 0 iff all checks pass with worst margin >= 30 mm.

    python3 scripts/reachability_check.py
"""
import math
import os
import re
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
FILES = "abcdefgh"

# Annulus tolerances and the overall pass threshold (mm).
INNER_MARGIN = 20.0
OUTER_MARGIN = 30.0
PASS_MARGIN = 30.0


def _find(*relparts):
    """Locate a package file in the source tree, else the installed share dir."""
    cand = os.path.normpath(os.path.join(HERE, os.pardir, *relparts))
    if os.path.exists(cand):
        return cand
    try:
        from ament_index_python.packages import get_package_share_directory
        share = get_package_share_directory("chess_arm_description")
        cand = os.path.join(share, *relparts)
        if os.path.exists(cand):
            return cand
    except Exception:
        pass
    raise FileNotFoundError(os.path.join(*relparts))


def load_params():
    with open(_find("config", "arm_params.yaml")) as f:
        return yaml.safe_load(f)


def xacro_numeric_properties():
    """Return {name: float} for every plain-numeric <xacro:property> in arm_params.xacro."""
    text = open(_find("urdf", "arm_params.xacro")).read()
    props = {}
    for name, value in re.findall(r'name="([A-Za-z0-9_]+)"\s+value="([^"]*)"', text):
        try:
            props[name] = float(value)
        except ValueError:
            pass  # skip expression-valued properties like ${...}
    return props


def assert_xacro_matches(p):
    """Guard against arm_params.yaml and arm_params.xacro drifting apart."""
    x = xacro_numeric_properties()
    L = p["links_mm"]
    checks = [
        ("base_height", x["base_height"] * 1000.0, L["base_height"]),
        ("shoulder_z", x["shoulder_z"] * 1000.0, L["shoulder_z"]),
        ("upper_arm", x["upper_arm"] * 1000.0, L["upper_arm"]),
        ("forearm", x["forearm"] * 1000.0, L["forearm"]),
        ("wrist", x["wrist"] * 1000.0, L["wrist"]),
        ("tool_tip", x["tool_tip"] * 1000.0, L["tool_tip"]),
        ("base_x", x["base_x"] * 1000.0, p["base_world_mm"]["x"]),
        ("base_y", x["base_y"] * 1000.0, p["base_world_mm"]["y"]),
        ("square_size", x["square_size"] * 1000.0, p["board"]["square_size_mm"]),
    ]
    jmap = {"j1": "J1_base_yaw", "j2": "J2_shoulder_pitch", "j3": "J3_elbow_pitch",
            "j4": "J4_forearm_roll", "j5": "J5_wrist_pitch", "j6": "J6_wrist_roll"}
    for key, jn in jmap.items():
        checks.append((f"{key}_lo", x[f"{key}_lo"], p["joints"][jn]["lower_deg"]))
        checks.append((f"{key}_hi", x[f"{key}_hi"], p["joints"][jn]["upper_deg"]))

    bad = [(n, a, b) for n, a, b in checks if abs(a - b) > 1e-6]
    if bad:
        print("CONSISTENCY FAILURE: arm_params.xacro vs arm_params.yaml differ:")
        for n, a, b in bad:
            print(f"  {n}: xacro={a} yaml={b}")
        sys.exit(2)
    print("Consistency OK: arm_params.xacro matches arm_params.yaml "
          f"({len(checks)} values).")


class Model:
    def __init__(self, p):
        L = p["links_mm"]
        self.UA = L["upper_arm"]
        self.FA = L["forearm"]
        self.tool_offset = L["wrist"] + L["tool_tip"]
        self.shoulder_z_world = L["base_height"] + L["shoulder_z"]
        self.base_x = p["base_world_mm"]["x"]
        self.base_y = p["base_world_mm"]["y"]
        self.reach = self.UA + self.FA
        self.inner = abs(self.UA - self.FA)
        self.sq = p["board"]["square_size_mm"]
        self.zg = p["task_heights_mm"]["grasp_z"]
        self.zl = p["task_heights_mm"]["lift_z"]
        J = p["joints"]
        self.j1 = (J["J1_base_yaw"]["lower_deg"], J["J1_base_yaw"]["upper_deg"])
        self.j2 = (J["J2_shoulder_pitch"]["lower_deg"], J["J2_shoulder_pitch"]["upper_deg"])
        self.j3 = (J["J3_elbow_pitch"]["lower_deg"], J["J3_elbow_pitch"]["upper_deg"])
        gv = p["graveyard"]
        self.gy_rows = gv["rows_x_mm"]
        self.gy_col0 = gv["col0_y_mm"]
        self.gy_pitch = gv["pitch_mm"]

    def squares(self):
        for fi in range(8):
            for ri in range(8):
                yield f"{FILES[fi]}{ri + 1}", (fi - 3.5) * self.sq, (ri - 3.5) * self.sq

    def graveyard(self):
        n = 0
        for rx in self.gy_rows:
            for c in range(8):
                n += 1
                yield f"GY{n}", rx, self.gy_col0 + c * self.gy_pitch

    def ik(self, r, wc_z):
        """Elbow-up planar IK. Returns (D, j2_deg, j3_deg) or (D, None, None)."""
        a, b = r, wc_z - self.shoulder_z_world
        D = math.hypot(a, b)
        if D > self.reach or D < self.inner:
            return D, None, None
        cos_e = max(-1.0, min(1.0, (self.UA**2 + self.FA**2 - D**2) / (2 * self.UA * self.FA)))
        elbow_interior = math.degrees(math.acos(cos_e))   # 180 = straight
        phi = math.degrees(math.atan2(b, a))
        cos_s = max(-1.0, min(1.0, (self.UA**2 + D**2 - self.FA**2) / (2 * self.UA * D)))
        alpha_horiz = phi + math.degrees(math.acos(cos_s))  # upper-arm angle from horizontal
        # Report J2 from the URDF zero (arm straight up, +Z; axis +Y) so the J2
        # limit gate is in URDF terms. Limits are symmetric, so the sign of the
        # +Y rotation does not affect the +/- bound check.
        j2 = 90.0 - alpha_horiz                             # shoulder pitch from straight-up
        j3 = -(180.0 - elbow_interior)                      # elbow-up bend (negative)
        return D, j2, j3

    def check(self, tx, ty, tz):
        wc_z = tz + self.tool_offset
        r = math.hypot(tx - self.base_x, ty - self.base_y)
        yaw = math.degrees(math.atan2(ty - self.base_y, tx - self.base_x))
        D, j2, j3 = self.ik(r, wc_z)
        fails = []
        if wc_z <= 0:
            fails.append("wc_z<=0")
        if not (self.inner + INNER_MARGIN <= D <= self.reach - OUTER_MARGIN):
            fails.append(f"D={D:.1f} outside annulus")
        if not (self.j1[0] <= yaw <= self.j1[1]):
            fails.append(f"yaw={yaw:.1f}")
        if j2 is None:
            fails.append("no IK")
        else:
            if not (self.j2[0] <= j2 <= self.j2[1]):
                fails.append(f"j2={j2:.1f}")
            if not (self.j3[0] <= j3 <= self.j3[1]):
                fails.append(f"j3={j3:.1f}")
        return (not fails), self.reach - D, fails


def main():
    p = load_params()
    assert_xacro_matches(p)
    m = Model(p)

    print("=" * 74)
    print("CHESS ARM REACHABILITY CHECK")
    print(f"  upper_arm={m.UA} forearm={m.FA} reach={m.reach} inner={m.inner} mm")
    print(f"  tool_offset={m.tool_offset}  shoulder_z_world={m.shoulder_z_world}")
    print(f"  base=({m.base_x},{m.base_y})  grasp_z={m.zg} lift_z={m.zl}")
    print(f"  annulus=[{m.inner + INNER_MARGIN:.0f},{m.reach - OUTER_MARGIN:.0f}] mm")
    print("=" * 74)

    targets = [("sq", n, x, y) for n, x, y in m.squares()]
    n_sq = len(targets)
    targets += [("gy", n, x, y) for n, x, y in m.graveyard()]
    n_gy = len(targets) - n_sq

    total = passed = 0
    worst = (1e9, None, None)
    margins = []
    failures = []
    for kind, name, x, y in targets:
        for hl, z in (("grasp", m.zg), ("lift", m.zl)):
            total += 1
            ok, margin, fails = m.check(x, y, z)
            margins.append((margin, name, hl))
            if ok:
                passed += 1
                if margin < worst[0]:
                    worst = (margin, name, hl)
            else:
                failures.append((name, hl, kind, margin, fails))

    margins.sort()
    print(f"\nSquares: {n_sq}   Graveyard slots: {n_gy}   Checks (x2 heights): {total}")
    print(f"PASSED: {passed}/{total}   FAILURES: {len(failures)}")
    if failures:
        print("\n-- FAILURES (first 20) --")
        for name, hl, kind, margin, fails in failures[:20]:
            print(f"  {name:>4} {hl:<5} margin={margin:7.1f}  {fails}")
    print(f"\nWorst margin among reachable: {worst[0]:.1f} mm at {worst[1]} ({worst[2]})")
    print("-- 6 smallest margins --")
    for margin, name, hl in margins[:6]:
        print(f"  {name:>4} {hl:<5} margin={margin:7.1f}")

    ok = not failures and worst[0] >= PASS_MARGIN
    print("\n" + "=" * 74)
    print(f"RESULT: {'ALL PASS (worst >= %.0fmm) -> OK' % PASS_MARGIN if ok else 'NOT OK'}")
    print("=" * 74)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
