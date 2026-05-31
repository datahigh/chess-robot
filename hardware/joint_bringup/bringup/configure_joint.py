#!/usr/bin/env python3
# =============================================================================
# configure_joint.py  --  apply the wrist-joint moteus config via moteus_tool
# =============================================================================
"""Thin, auditable wrapper that documents (in code) HOW the Phase-1 wrist
joint's moteus-c1 config is applied. It shells out to the installed
`moteus.moteus_tool` to push ../config/wrist_joint.cfg onto the controller and
`conf write` it to flash.

WHY A WRAPPER: the apply step is a one-liner, but it has a sharp edge worth
encoding once. Our config file (wrist_joint.cfg) is HEAVILY COMMENTED. Two
moteus_tool verbs can load a config and they treat comments differently:

    --restore-config <file>   prepends `conf set` to each line, STRIPS `#`
                              comments, then runs `conf write`.  <-- USE THIS
                              for the commented wrist_joint.cfg.

    --write-config <file>     sends each line VERBATIM (does NOT strip `#`),
                              intended for an exact `--dump-config` snapshot.

The task asked for `--write-config`; that is correct ONLY for a verbatim dump.
For our annotated source file you MUST use `--restore-config` or the comment
text is sent as register values and the device rejects the lines. This script
therefore DEFAULTS to --restore-config (matching the file it ships with) and
exposes `--mode write` for the verbatim-dump case.

IMPORTANT (ORDER): this applies ONLY the geometry / AS5047P-output-source /
safety-limit registers. Motor-calibration-derived registers (motor.poles,
servo.pid_dq.*, servo.encoder_filter.*, the commutation sign/offset) are NOT in
this file -- they are written by `moteus_tool --calibrate` and MUST be on the
device FIRST. See ../docs/calibration_and_tuning.md for the full sequence.

By default this PRINTS the exact command and runs it. Use --dry-run to print
without executing (useful with no hardware / before `usbipd attach`).

WSL2 note: requires the fdcanusb attached (`usbipd attach --wsl --busid <id>`
on Windows). Native on the Pi 5. With no device, run with --dry-run; the live
run will surface moteus_tool's own transport error.

Usage:
    # default: restore the commented wrist_joint.cfg to target 1, then write flash
    python3 configure_joint.py

    # just print the command, do not execute (safe with no hardware):
    python3 configure_joint.py --dry-run

    # apply a verbatim --dump-config snapshot instead:
    python3 configure_joint.py --mode write --config /path/to/snapshot.cfg

    # different node id / explicit transport:
    python3 configure_joint.py --target 1 --fdcanusb /dev/fdcanusb
"""

import argparse
import os
import subprocess
import sys


# ../config/wrist_joint.cfg relative to this file (bringup/ -> ../config/).
_HERE = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_CFG = os.path.normpath(
    os.path.join(_HERE, "..", "config", "wrist_joint.cfg"))

# Map our --mode to the moteus_tool flag.
#   restore -> --restore-config (strips comments)  [default, for our cfg]
#   write   -> --write-config   (verbatim)         [for dump snapshots only]
_MODE_FLAG = {
    "restore": "--restore-config",
    "write": "--write-config",
}


def build_command(args):
    """Build the moteus_tool argv list (no shell). Verified flags:
       python3 -m moteus.moteus_tool --target N {--restore-config|--write-config} FILE
       optional: --fdcanusb PATH (moteus_tool's transport selector).
    """
    cmd = [
        sys.executable, "-m", "moteus.moteus_tool",
        "--target", str(args.target),
    ]
    # Let moteus_tool pick the transport; pass --fdcanusb only if specified.
    # (moteus_tool exposes --fdcanusb PATH via make_transport_args.)
    if args.fdcanusb:
        cmd += ["--fdcanusb", args.fdcanusb]
    cmd += [_MODE_FLAG[args.mode], args.config]
    return cmd


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Apply the wrist-joint moteus config via moteus_tool "
                    "(restore = strips comments; write = verbatim dump).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--target", type=int, default=1,
                   help="moteus CAN node id of the wrist joint")
    p.add_argument("--fdcanusb", default=None, metavar="PATH",
                   help="serial path of the fdcanusb (default: moteus_tool auto-detect)")
    p.add_argument("--config", default=_DEFAULT_CFG, metavar="CFG",
                   help="config file to apply")
    p.add_argument("--mode", choices=("restore", "write"), default="restore",
                   help="restore = --restore-config (strips comments; use for "
                        "the shipped commented cfg); write = --write-config "
                        "(verbatim; use only for a --dump-config snapshot)")
    p.add_argument("--dry-run", action="store_true",
                   help="print the command but do NOT execute it")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    if not os.path.isfile(args.config):
        sys.stderr.write(f"ERROR: config file not found: {args.config}\n")
        return 2

    if args.mode == "write" and args.config == _DEFAULT_CFG:
        sys.stderr.write(
            "WARNING: --mode write sends lines VERBATIM and will NOT strip the "
            "comments in the shipped wrist_joint.cfg.\n"
            "         Use the default --mode restore for that file. Continuing "
            "only because you asked.\n"
        )

    cmd = build_command(args)
    printable = " ".join(cmd)
    print("Applying wrist-joint config:")
    print(f"  file   : {args.config}")
    print(f"  mode   : {args.mode}  ({_MODE_FLAG[args.mode]})")
    print(f"  target : {args.target}")
    print("  command:")
    print(f"    {printable}")

    if args.dry_run:
        print("\n[--dry-run] not executed.")
        return 0

    print()
    try:
        completed = subprocess.run(cmd)
    except FileNotFoundError as e:
        # python -m moteus.moteus_tool not importable -> moteus not installed.
        sys.stderr.write(
            f"ERROR: could not launch moteus_tool: {e}\n"
            "       Is the `moteus` package installed in this interpreter?\n"
        )
        return 2
    except KeyboardInterrupt:
        return 130

    if completed.returncode != 0:
        sys.stderr.write(
            f"\nERROR: moteus_tool exited {completed.returncode}. Common causes:\n"
            "       * fdcanusb not attached (WSL2: run `usbipd attach` first)\n"
            "       * wrong --target id / device not powered\n"
            "       * used --mode write on a commented file (use restore)\n"
        )
    else:
        print("\nOK: config applied and `conf write` committed to flash.")
    return completed.returncode


if __name__ == "__main__":
    sys.exit(main())
