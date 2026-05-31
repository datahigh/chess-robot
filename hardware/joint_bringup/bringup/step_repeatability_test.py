#!/usr/bin/env python3
# =============================================================================
# step_repeatability_test.py  --  Phase-1 wrist-joint ACCEPTANCE test
# =============================================================================
"""Acceptance test for ONE bench wrist-class joint (gimbal BLDC + single-stage
~9:1 cycloidal reducer + AS5047P-on-aux2 absolute OUTPUT encoder, driven by a
moteus-c1 over fdcanusb).

WHAT IT PROVES
  * Static accuracy   : how close the settled OUTPUT position is to commanded.
  * Repeatability     : spread of repeated visits to the SAME target.
  * Backlash/hysteresis: difference between APPROACH-FROM-BELOW and
                         APPROACH-FROM-ABOVE settled positions at each target
                         (the dominant error term for a printed cycloidal joint).

HOW IT MEASURES
  The moteus reports `position` from the aux2 AS5047P, i.e. true OUTPUT-shaft
  revolutions (because motor_position.output.source = 1 and
  rotor_to_output_ratio = 1/9 are configured). So commanded and measured are
  apples-to-apples in OUTPUT revs. All angles in this script are OUTPUT-shaft
  DEGREES on the CLI/CSV; commands to moteus use OUTPUT revolutions (deg/360).

MOTION PROFILE (deliberately conservative -- low-torque bench joint)
  Each setpoint is a position-mode command with explicit limits:
    velocity_limit (out-rev/s), accel_limit (out-rev/s^2), maximum_torque (Nm),
    and a per-command watchdog_timeout so a dropped CAN link stops the joint.
  We hold velocity=0 at the target (a pure position hold) and settle before
  reading. These never exceed the on-device servo.max_* and servopos limits.

SAFETY
  * The CLI does NOT silently clamp commands; it ABORTS (exit 2) before any
    motion if |--min-deg| or |--max-deg| exceeds --servopos-limit-deg (default
    72 deg = the cfg's servopos +/-0.2 rev). Keep --servopos-limit-deg in sync
    with the device's servopos.position_min/max -- that on-device limit is the
    real backstop and hard-saturates motion regardless of what is commanded.
  * On any fault, serial loss, or Ctrl-C we send set_stop() and exit non-zero.
  * Default torque cap is tiny (0.1 Nm) -- raise only deliberately.

NO HARDWARE: imports + --help cleanly with no device; a live run prints a clear
transport error and exits 2 (WSL2: `usbipd attach` first; native on the Pi 5).

PASS/FAIL
  PASS iff, across all targets:
      max repeatability spread <= --repeatability-deg AND
      max |mean accuracy error| <= --accuracy-deg.
  Backlash is REPORTED (and compared to --backlash-deg if given) but, unless
  --fail-on-backlash is set, it does not by itself fail the run -- backlash is
  expected pre-tuning and informs gear/compensation work.

Usage:
    # dry, no hardware -- prints the plan + thresholds and exits:
    python3 step_repeatability_test.py --plan-only

    # real run against target 1, +/-30 deg, 5 targets, 4 repeats each:
    python3 step_repeatability_test.py --target 1 \
        --min-deg -30 --max-deg 30 --steps 5 --repeats 4 \
        --repeatability-deg 0.5 --accuracy-deg 1.0 --csv wrist_accept.csv

Verified moteus 1.0.0 API used (introspected, not guessed):
    moteus.Fdcanusb(path=...)
    moteus.Controller(id=, transport=, query_resolution=)
    Controller.make_position(position=, velocity=, maximum_torque=,
        velocity_limit=, accel_limit=, watchdog_timeout=, query=True)
    await Controller.set_position(...)        # = execute(make_position(...))
    await Controller.set_stop()
    await Controller.query()
    Result.values[moteus.Register.{POSITION,VELOCITY,MODE,FAULT,...}]
    moteus.Mode(int); moteus.F32
"""

import argparse
import asyncio
import math
import statistics
import sys
import time


import moteus

try:
    import serial  # pyserial
    _NO_DEVICE_ERRORS = (serial.SerialException, OSError, IndexError, RuntimeError)
except Exception:  # pragma: no cover
    _NO_DEVICE_ERRORS = (OSError, IndexError, RuntimeError)


# --- unit helpers ------------------------------------------------------------
def deg_to_rev(d):
    return d / 360.0


def rev_to_deg(r):
    return r * 360.0


# --- query resolution --------------------------------------------------------
def build_query_resolution():
    qr = moteus.QueryResolution()
    qr.q_current = moteus.F32
    return qr


# --- transport ---------------------------------------------------------------
def make_transport(path):
    return moteus.Fdcanusb(path=path)


# --- target sequence ---------------------------------------------------------
def build_targets(min_deg, max_deg, steps):
    """Evenly spaced targets across [min_deg, max_deg] (OUTPUT degrees)."""
    if steps < 2:
        return [min_deg, max_deg]
    span = max_deg - min_deg
    return [min_deg + span * i / (steps - 1) for i in range(steps)]


def build_visit_plan(targets, repeats):
    """Build an ordered list of (target_deg, approach) visits.

    'approach' is 'up' (arrived moving in +deg) or 'down' (arrived moving in
    -deg). We expose backlash by sweeping the full target list UP then DOWN,
    `repeats` times. The first move of each sweep is tagged by sweep direction.

    Returns list of dicts: {idx, target_deg, approach, sweep}.
    """
    plan = []
    for s in range(repeats):
        # ascending sweep -> every arrival approached from below = 'up'
        for t in targets:
            plan.append({"target_deg": t, "approach": "up", "sweep": s})
        # descending sweep -> arrivals approached from above = 'down'
        for t in reversed(targets):
            plan.append({"target_deg": t, "approach": "down", "sweep": s})
    for i, v in enumerate(plan):
        v["idx"] = i
    return plan


# --- one settled move --------------------------------------------------------
async def move_and_settle(controller, target_deg, args):
    """Command a position hold at target_deg (OUTPUT deg), wait for settle,
    return the settled measured position in OUTPUT deg.

    Settle criterion: |velocity| < settle_vel and |measured-target| stable, or
    the settle timeout elapses. We re-issue the command each loop so the
    per-command watchdog stays fed during the hold.
    """
    target_rev = deg_to_rev(target_deg)
    vel_lim = deg_to_rev(args.velocity_deg)         # out-rev/s
    accel_lim = deg_to_rev(args.accel_deg)          # out-rev/s^2
    settle_vel_rev = deg_to_rev(args.settle_vel_deg)

    t0 = time.monotonic()
    last_pos_deg = None
    measured_deg = math.nan

    while True:
        result = await controller.set_position(
            position=target_rev,
            velocity=0.0,                  # pure position hold at the target
            maximum_torque=args.max_torque,
            velocity_limit=vel_lim,
            accel_limit=accel_lim,
            watchdog_timeout=args.watchdog,
            query=True,
        )
        v = result.values
        fault = v.get(moteus.Register.FAULT, 0)
        if fault not in (0, None):
            raise RuntimeError(f"controller FAULT {fault} during move to "
                               f"{target_deg:.3f} deg")

        pos = v.get(moteus.Register.POSITION)
        vel = v.get(moteus.Register.VELOCITY)
        if pos is not None:
            measured_deg = rev_to_deg(pos)

        elapsed = time.monotonic() - t0
        slow = (vel is not None and abs(vel) < settle_vel_rev)
        stable = (last_pos_deg is not None
                  and pos is not None
                  and abs(rev_to_deg(pos) - last_pos_deg) < args.settle_band_deg)
        last_pos_deg = measured_deg

        if elapsed >= args.settle_min_s and slow and stable:
            break
        if elapsed >= args.settle_timeout_s:
            break
        await asyncio.sleep(args.poll_period_s)

    # brief dwell read to reject the last in-motion sample
    await asyncio.sleep(args.dwell_s)
    result = await controller.query()
    pos = result.values.get(moteus.Register.POSITION)
    if pos is not None:
        measured_deg = rev_to_deg(pos)
    return measured_deg


# --- stats -------------------------------------------------------------------
def _bucket_key(target_deg, tol=1e-6):
    # group visits to the "same" commanded target (floats) robustly
    return round(target_deg, 4)


def summarize(records):
    """records: list of dicts {target_deg, approach, measured_deg, error_deg}.
    Returns (per_target_stats, overall) where per_target_stats is a list of
    dicts and overall has worst-case repeatability / accuracy / backlash.
    """
    by_target = {}
    for r in records:
        by_target.setdefault(_bucket_key(r["target_deg"]), []).append(r)

    per_target = []
    worst_repeat = 0.0
    worst_abs_mean_err = 0.0
    worst_backlash = 0.0

    for key in sorted(by_target):
        rs = by_target[key]
        measured = [r["measured_deg"] for r in rs if not math.isnan(r["measured_deg"])]
        errors = [r["error_deg"] for r in rs if not math.isnan(r["error_deg"])]
        ups = [r["measured_deg"] for r in rs
               if r["approach"] == "up" and not math.isnan(r["measured_deg"])]
        downs = [r["measured_deg"] for r in rs
                 if r["approach"] == "down" and not math.isnan(r["measured_deg"])]

        if measured:
            repeat_spread = max(measured) - min(measured)
            mean_err = statistics.fmean(errors) if errors else math.nan
            std_err = statistics.pstdev(errors) if len(errors) > 1 else 0.0
        else:
            repeat_spread = math.nan
            mean_err = math.nan
            std_err = math.nan

        # backlash: mean(up arrivals) - mean(down arrivals) at this target
        if ups and downs:
            backlash = statistics.fmean(ups) - statistics.fmean(downs)
        else:
            backlash = math.nan

        per_target.append({
            "target_deg": rs[0]["target_deg"],
            "n": len(measured),
            "mean_err_deg": mean_err,
            "std_err_deg": std_err,
            "repeat_spread_deg": repeat_spread,
            "backlash_deg": backlash,
        })

        if not math.isnan(repeat_spread):
            worst_repeat = max(worst_repeat, repeat_spread)
        if not math.isnan(mean_err):
            worst_abs_mean_err = max(worst_abs_mean_err, abs(mean_err))
        if not math.isnan(backlash):
            worst_backlash = max(worst_backlash, abs(backlash))

    overall = {
        "worst_repeatability_deg": worst_repeat,
        "worst_abs_mean_error_deg": worst_abs_mean_err,
        "worst_abs_backlash_deg": worst_backlash,
    }
    return per_target, overall


def write_csv(path, records):
    import csv
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["idx", "sweep", "target_deg", "approach",
                    "measured_deg", "error_deg"])
        for r in records:
            w.writerow([r["idx"], r["sweep"], f"{r['target_deg']:.6f}",
                        r["approach"], f"{r['measured_deg']:.6f}",
                        f"{r['error_deg']:.6f}"])


def print_report(per_target, overall, args):
    print()
    print("=== per-target statistics (OUTPUT degrees) ".ljust(70, "="))
    hdr = (f"{'target':>9} {'n':>3} {'mean_err':>9} {'std_err':>8} "
           f"{'repeat':>8} {'backlash':>9}")
    print(hdr)
    for t in per_target:
        def f(x, p=4):
            return f"{x:.{p}f}" if not math.isnan(x) else "  n/a"
        print(f"{t['target_deg']:9.3f} {t['n']:3d} "
              f"{f(t['mean_err_deg']):>9} {f(t['std_err_deg']):>8} "
              f"{f(t['repeat_spread_deg']):>8} {f(t['backlash_deg']):>9}")

    print()
    print("=== worst-case (OUTPUT degrees) ".ljust(70, "="))
    print(f"  repeatability spread : {overall['worst_repeatability_deg']:.4f} deg "
          f"(threshold {args.repeatability_deg:.4f})")
    print(f"  |mean accuracy error|: {overall['worst_abs_mean_error_deg']:.4f} deg "
          f"(threshold {args.accuracy_deg:.4f})")
    bl_thr = (f"(threshold {args.backlash_deg:.4f}"
              f"{', FAIL-ON' if args.fail_on_backlash else ', report-only'})"
              if args.backlash_deg is not None else "(report-only)")
    print(f"  |backlash| up vs down: {overall['worst_abs_backlash_deg']:.4f} deg {bl_thr}")


def evaluate(overall, args):
    """Return (passed: bool, reasons: list[str])."""
    reasons = []
    if overall["worst_repeatability_deg"] > args.repeatability_deg:
        reasons.append(
            f"repeatability {overall['worst_repeatability_deg']:.4f} > "
            f"{args.repeatability_deg:.4f} deg")
    if overall["worst_abs_mean_error_deg"] > args.accuracy_deg:
        reasons.append(
            f"accuracy {overall['worst_abs_mean_error_deg']:.4f} > "
            f"{args.accuracy_deg:.4f} deg")
    if (args.backlash_deg is not None and args.fail_on_backlash
            and overall["worst_abs_backlash_deg"] > args.backlash_deg):
        reasons.append(
            f"backlash {overall['worst_abs_backlash_deg']:.4f} > "
            f"{args.backlash_deg:.4f} deg")
    return (len(reasons) == 0), reasons


# --- run ---------------------------------------------------------------------
async def run(args):
    targets = build_targets(args.min_deg, args.max_deg, args.steps)
    plan = build_visit_plan(targets, args.repeats)

    print("Wrist-joint repeatability/backlash acceptance test")
    print(f"  target id     : {args.target}")
    print(f"  travel window : [{args.min_deg:.2f}, {args.max_deg:.2f}] OUTPUT deg")
    print(f"  targets ({len(targets)}): "
          + ", ".join(f"{t:.2f}" for t in targets))
    print(f"  repeats       : {args.repeats}  (up+down sweep each) "
          f"-> {len(plan)} visits")
    print(f"  velocity/accel: {args.velocity_deg:.2f} deg/s, "
          f"{args.accel_deg:.2f} deg/s^2")
    print(f"  max torque    : {args.max_torque:.3f} Nm   "
          f"watchdog: {args.watchdog:.2f} s")
    print(f"  thresholds    : repeatability<={args.repeatability_deg:.3f}, "
          f"accuracy<={args.accuracy_deg:.3f} deg")
    print(f"  servopos limit: +/-{args.servopos_limit_deg:.2f} OUTPUT deg "
          f"(must match device servopos.position_min/max)")

    # sanity: keep the window non-degenerate
    if args.max_deg <= args.min_deg:
        sys.stderr.write("ERROR: --max-deg must be greater than --min-deg\n")
        return 2

    # SAFETY: refuse (do not clamp) a window outside the device servopos band.
    # The on-device servopos.position_min/max is the real backstop, but aborting
    # here prevents commanding the joint to saturate against its software limit.
    worst = max(abs(args.min_deg), abs(args.max_deg))
    if worst > args.servopos_limit_deg:
        sys.stderr.write(
            f"ERROR: travel window |{worst:.2f}| deg exceeds --servopos-limit-deg "
            f"{args.servopos_limit_deg:.2f}; widen servopos.position_min/max on the "
            f"device first (and raise --servopos-limit-deg to match), or shrink the "
            f"--min-deg/--max-deg window.\n")
        return 2

    if args.plan_only:
        print("\n[--plan-only] no device touched.")
        return 0

    try:
        transport = make_transport(args.fdcanusb)
    except _NO_DEVICE_ERRORS as e:
        sys.stderr.write(
            "ERROR: could not open the fdcanusb transport.\n"
            f"       {type(e).__name__}: {e}\n"
            "       WSL2: run `usbipd attach --wsl --busid <id>` on Windows "
            "first; native on the Pi 5.\n"
            "       Or pass --fdcanusb /dev/ttyACM0 .\n"
        )
        return 2

    controller = moteus.Controller(
        id=args.target,
        transport=transport,
        query_resolution=build_query_resolution(),
    )

    records = []
    rc = 0
    try:
        # Clear faults / known state, then read the start position.
        await controller.set_stop()
        start = await controller.query()
        start_pos = start.values.get(moteus.Register.POSITION)
        if start_pos is not None:
            print(f"  start position: {rev_to_deg(start_pos):.4f} OUTPUT deg")

        for v in plan:
            measured = await move_and_settle(controller, v["target_deg"], args)
            err = measured - v["target_deg"]
            rec = {
                "idx": v["idx"], "sweep": v["sweep"],
                "target_deg": v["target_deg"], "approach": v["approach"],
                "measured_deg": measured, "error_deg": err,
            }
            records.append(rec)
            print(f"  visit {v['idx']:3d} [{v['approach']:>4}] "
                  f"cmd {v['target_deg']:8.3f}  meas {measured:8.3f}  "
                  f"err {err:+.4f} deg")

    except _NO_DEVICE_ERRORS as e:
        sys.stderr.write(f"\nERROR: serial/transport lost during test: "
                         f"{type(e).__name__}: {e}\n")
        rc = 2
    except moteus.CommandError as e:
        sys.stderr.write(f"\nERROR: moteus command error (no reply / bad id?): {e}\n")
        rc = 3
    except RuntimeError as e:
        sys.stderr.write(f"\nERROR: {e}\n")
        rc = 4
    except KeyboardInterrupt:
        sys.stderr.write("\nINTERRUPTED -- stopping joint.\n")
        rc = 130
    finally:
        # Always leave the joint safe.
        try:
            await controller.set_stop()
        except Exception:
            pass

    if not records:
        sys.stderr.write("No measurements captured; cannot evaluate.\n")
        return rc or 5

    per_target, overall = summarize(records)
    print_report(per_target, overall, args)

    if args.csv:
        write_csv(args.csv, records)
        print(f"\nwrote {len(records)} rows -> {args.csv}")

    passed, reasons = evaluate(overall, args)
    print()
    if passed:
        print("RESULT: PASS")
    else:
        print("RESULT: FAIL")
        for r in reasons:
            print(f"  - {r}")
        rc = rc or 1

    return rc


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Phase-1 wrist-joint position repeatability / backlash "
                    "acceptance test (OUTPUT-shaft degrees).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    # transport / target
    p.add_argument("--target", type=int, default=1,
                   help="moteus CAN node id of the wrist joint")
    p.add_argument("--fdcanusb", default=None, metavar="PATH",
                   help="serial path of the fdcanusb (default: auto-detect)")

    # test window / pattern (OUTPUT degrees)
    p.add_argument("--min-deg", type=float, default=-20.0,
                   help="lowest target, OUTPUT deg (keep inside servopos.position_min)")
    p.add_argument("--max-deg", type=float, default=20.0,
                   help="highest target, OUTPUT deg (keep inside servopos.position_max)")
    p.add_argument("--servopos-limit-deg", type=float, default=72.0,
                   help="abort before motion if |min/max-deg| exceeds this; "
                        "keep == device servopos.position_min/max (72 deg = +/-0.2 rev)")
    p.add_argument("--steps", type=int, default=5,
                   help="number of distinct targets across the window")
    p.add_argument("--repeats", type=int, default=4,
                   help="up+down sweeps (each visits every target twice)")

    # motion limits (conservative; never exceed on-device servo.max_*)
    p.add_argument("--velocity-deg", type=float, default=60.0,
                   help="velocity_limit, OUTPUT deg/s")
    p.add_argument("--accel-deg", type=float, default=120.0,
                   help="accel_limit, OUTPUT deg/s^2")
    p.add_argument("--max-torque", type=float, default=0.1,
                   help="maximum_torque per position command, Nm (keep tiny)")
    p.add_argument("--watchdog", type=float, default=0.5,
                   help="per-command watchdog_timeout, s (dropped link -> stop)")

    # settle behaviour
    p.add_argument("--settle-vel-deg", type=float, default=1.0,
                   help="|velocity| below this counts as settled, OUTPUT deg/s")
    p.add_argument("--settle-band-deg", type=float, default=0.02,
                   help="position must be stable within this band, OUTPUT deg")
    p.add_argument("--settle-min-s", type=float, default=0.4,
                   help="minimum dwell before accepting settle, s")
    p.add_argument("--settle-timeout-s", type=float, default=4.0,
                   help="give up waiting for settle after this, s")
    p.add_argument("--dwell-s", type=float, default=0.15,
                   help="quiet dwell before the final measurement read, s")
    p.add_argument("--poll-period-s", type=float, default=0.02,
                   help="command/telemetry loop period during a move, s")

    # pass/fail thresholds (OUTPUT degrees)
    p.add_argument("--repeatability-deg", type=float, default=0.5,
                   help="PASS if worst repeat spread <= this, OUTPUT deg")
    p.add_argument("--accuracy-deg", type=float, default=1.0,
                   help="PASS if worst |mean error| <= this, OUTPUT deg")
    p.add_argument("--backlash-deg", type=float, default=None,
                   help="optional backlash threshold, OUTPUT deg (report-only "
                        "unless --fail-on-backlash)")
    p.add_argument("--fail-on-backlash", action="store_true",
                   help="also FAIL if worst |backlash| exceeds --backlash-deg")

    # output / dry
    p.add_argument("--csv", default=None, metavar="PATH",
                   help="write per-visit commanded/measured log to CSV")
    p.add_argument("--plan-only", action="store_true",
                   help="print the plan + thresholds and exit (no device)")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        return asyncio.run(run(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
