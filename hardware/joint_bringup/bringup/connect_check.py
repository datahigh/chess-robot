#!/usr/bin/env python3
# =============================================================================
# connect_check.py  --  Phase-1 wrist-joint moteus-c1 liveness / telemetry check
# =============================================================================
"""Connect to the Phase-1 wrist-class joint's moteus-c1 over fdcanusb, stop it,
query it, and print a readable telemetry block (mode / fault / position /
velocity / temperature / voltage / q_current).

This is the FIRST script to run after wiring the bench joint. It does NOT move
the motor: it sends a `set_stop` (clears any latched fault / holds the joint
unpowered) and then a single `query`. With `--watch` it polls in a loop.

Context (see ../config/wrist_joint.cfg, ../docs):
  * One bench joint: gimbal BLDC + single-stage ~9:1 cycloidal reducer.
  * Onboard encoder (aux1) = commutation source; external AS5047P (14-bit SPI,
    aux2) = absolute OUTPUT-shaft position source.
  * After `motor_position.rotor_to_output_ratio` (= 1/9) is applied, the
    reported `position`/`velocity` are in OUTPUT-shaft revolutions.

WSL2 note: the fdcanusb only appears as /dev/fdcanusb (or /dev/ttyACM*) AFTER
`usbipd attach --wsl --busid <id>` is run on the Windows host. On the Raspberry
Pi 5 deployment brain it is native. With NO device attached this script still
imports and `--help`s cleanly; a live connect prints a clear error and exits 2.

Usage:
    # default transport (auto-detect fdcanusb), CAN id 1:
    python3 connect_check.py

    # explicit serial path + target, poll at 5 Hz:
    python3 connect_check.py --fdcanusb /dev/fdcanusb --target 1 --watch --hz 5

Verified moteus 1.0.0 API used here (introspected, not guessed):
    moteus.Fdcanusb(path=...)                 # transport; opens serial in ctor
    moteus.Controller(id=, transport=, query_resolution=)
    moteus.QueryResolution()                  # fields: mode/position/velocity/
                                              #   torque/voltage/temperature/
                                              #   fault default-enabled; we also
                                              #   enable q_current + abs_position
    await Controller.set_stop()               # -> make_stop()/execute()
    await Controller.query()                  # -> Result.values[Register.X]
    moteus.Register.{MODE,FAULT,POSITION,VELOCITY,TEMPERATURE,VOLTAGE,
                     Q_CURRENT,ABS_POSITION,TORQUE,POWER}
    moteus.Mode(int)                          # decode mode enum
    moteus.F32 / INT16 / INT8 / IGNORE        # resolution constants
"""

import argparse
import asyncio
import sys

import moteus


# Exceptions that mean "no fdcanusb present / cannot open the serial port".
# Verified empirically against moteus 1.0.0 + pyserial 3.5:
#   * explicit missing path  -> serial.SerialException
#   * auto-detect, no device -> IndexError (detect_fdcanusb glob is empty)
# OSError/RuntimeError are caught defensively for other USB/serial faults.
try:
    import serial  # pyserial; pulled in transitively by moteus
    _NO_DEVICE_ERRORS = (serial.SerialException, OSError, IndexError, RuntimeError)
except Exception:  # pragma: no cover - pyserial should always be present
    _NO_DEVICE_ERRORS = (OSError, IndexError, RuntimeError)


def build_query_resolution():
    """A QueryResolution that adds q_current + abs_position to the defaults.

    Defaults already enable mode/position/velocity/torque/voltage/temperature/
    fault (verified by decoding moteus.QueryResolution()). We add the rotor-side
    current and the raw abs-position for richer bring-up diagnostics.
    """
    qr = moteus.QueryResolution()
    qr.q_current = moteus.F32
    qr.abs_position = moteus.F32
    return qr


def make_transport(fdcanusb_path):
    """Construct the fdcanusb transport, opening the serial port now so we can
    fail fast with a clear message if no device is attached.

    Returns the transport, or raises one of _NO_DEVICE_ERRORS.
    """
    # path=None -> moteus auto-detects /dev/fdcanusb-style devices.
    return moteus.Fdcanusb(path=fdcanusb_path)


def _get(values, register, default=None):
    """Safely read a register out of a query Result.values dict."""
    return values.get(register, default)


def format_telemetry(result):
    """Render a query Result into a readable multi-line block."""
    v = result.values
    mode_raw = _get(v, moteus.Register.MODE)
    try:
        mode_name = moteus.Mode(int(mode_raw)).name if mode_raw is not None else "?"
    except (ValueError, TypeError):
        mode_name = "UNKNOWN"

    fault = _get(v, moteus.Register.FAULT)
    pos = _get(v, moteus.Register.POSITION)        # OUTPUT-shaft revs (post-ratio)
    vel = _get(v, moteus.Register.VELOCITY)        # OUTPUT revs/s
    temp = _get(v, moteus.Register.TEMPERATURE)    # board temp, deg C
    mtemp = _get(v, moteus.Register.MOTOR_TEMPERATURE)
    volt = _get(v, moteus.Register.VOLTAGE)        # bus voltage, V
    iq = _get(v, moteus.Register.Q_CURRENT)        # q-axis current, A
    torque = _get(v, moteus.Register.TORQUE)       # estimated output torque, Nm
    abs_pos = _get(v, moteus.Register.ABS_POSITION)

    def fmt(x, prec=4, unit=""):
        if x is None:
            return "n/a"
        try:
            return f"{x:.{prec}f}{unit}"
        except (ValueError, TypeError):
            return f"{x}{unit}"

    fault_str = "0 (none)" if fault in (0, None) else f"{fault}  <-- FAULT"

    lines = [
        f"  can id        : {result.id}",
        f"  mode          : {mode_raw} ({mode_name})",
        f"  fault         : {fault_str}",
        f"  position      : {fmt(pos)} out-rev   (OUTPUT shaft, post 1/9 ratio)",
        f"  velocity      : {fmt(vel)} out-rev/s",
        f"  torque (est)  : {fmt(torque)} Nm",
        f"  q_current     : {fmt(iq, 3)} A",
        f"  voltage (bus) : {fmt(volt, 2)} V",
        f"  temp (board)  : {fmt(temp, 1)} C",
        f"  temp (motor)  : {fmt(mtemp, 1)} C",
        f"  abs_position  : {fmt(abs_pos)}",
    ]
    return "\n".join(lines)


async def run(args):
    try:
        transport = make_transport(args.fdcanusb)
    except _NO_DEVICE_ERRORS as e:
        sys.stderr.write(
            "ERROR: could not open the fdcanusb transport.\n"
            f"       {type(e).__name__}: {e}\n"
            "       * On WSL2, run `usbipd attach --wsl --busid <id>` on Windows\n"
            "         first so /dev/fdcanusb (or /dev/ttyACM*) appears.\n"
            "       * Pass an explicit path with --fdcanusb /dev/ttyACM0 .\n"
            "       * On the Raspberry Pi 5 the device is native (no attach).\n"
        )
        return 2

    controller = moteus.Controller(
        id=args.target,
        transport=transport,
        query_resolution=build_query_resolution(),
    )

    try:
        # set_stop: hold the joint unpowered and clear any latched fault.
        await controller.set_stop()

        period = 1.0 / args.hz if args.hz > 0 else 0.2
        first = True
        while True:
            result = await controller.query()
            if not first:
                # ANSI: move cursor up to overwrite the previous block on --watch.
                if args.watch and sys.stdout.isatty():
                    sys.stdout.write(f"\x1b[{12}A")
            print("=== moteus-c1 wrist joint (target "
                  f"{args.target}) ".ljust(60, "="))
            print(format_telemetry(result))
            first = False
            if not args.watch:
                break
            await asyncio.sleep(period)
    except _NO_DEVICE_ERRORS as e:
        sys.stderr.write(
            f"ERROR: lost the fdcanusb / serial link during I/O.\n"
            f"       {type(e).__name__}: {e}\n"
        )
        return 2
    except moteus.CommandError as e:
        sys.stderr.write(f"ERROR: moteus command error (no reply / bad id?): {e}\n")
        return 3
    except KeyboardInterrupt:
        pass
    return 0


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Connect to the Phase-1 wrist joint moteus-c1 over fdcanusb, "
                    "stop it, and print telemetry.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--target", type=int, default=1,
                   help="moteus CAN node id of the wrist joint")
    p.add_argument("--fdcanusb", default=None, metavar="PATH",
                   help="serial path of the fdcanusb (default: auto-detect)")
    p.add_argument("--watch", action="store_true",
                   help="poll continuously instead of a single read")
    p.add_argument("--hz", type=float, default=5.0,
                   help="poll rate when --watch is set")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        return asyncio.run(run(args))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
