# Copyright 2026 neil
#
# Use of this source code is governed by an MIT-style
# license that can be found in the LICENSE file or at
# https://opensource.org/licenses/MIT.

"""Tests for the pluggable executors (no ROS required)."""

from chess_arm_orchestrator.executors import (
    describe_action,
    DryRunExecutor,
    Executor,
    make_executor,
    MoveItExecutor,
)
from chess_arm_orchestrator.piece_actions import PICK_PLACE, PieceActionData, Point
import pytest


def _sample_actions():
    return [
        PieceActionData(
            action_type=PICK_PLACE,
            from_square='e2', to_square='e4',
            from_xyz=Point(0.1, 0.2, 0.03),
            to_xyz=Point(0.1, 0.3, 0.03),
            piece='P',
        )
    ]


def test_dry_run_executes_and_succeeds():
    """The dry-run executor logs actions and returns True."""
    ex = DryRunExecutor()
    assert ex.execute(_sample_actions()) is True


def test_dry_run_empty_is_ok():
    """An empty action list is a no-op success."""
    ex = DryRunExecutor()
    assert ex.execute([]) is True


def test_moveit_stub_refuses():
    """The MoveIt stub refuses to run (returns False)."""
    ex = MoveItExecutor()
    assert ex.execute(_sample_actions()) is False


def test_factory_selects_dry_run_by_default():
    """The factory defaults to DryRunExecutor."""
    assert isinstance(make_executor('dry_run'), DryRunExecutor)
    assert isinstance(make_executor(None), DryRunExecutor)


def test_factory_selects_moveit():
    """The factory builds a MoveItExecutor on request."""
    assert isinstance(make_executor('moveit'), MoveItExecutor)


def test_factory_rejects_unknown():
    """An unknown executor name raises ValueError."""
    with pytest.raises(ValueError):
        make_executor('teleport')


def test_describe_action_smoke():
    """describe_action renders the action type and squares."""
    text = describe_action(_sample_actions()[0])
    assert 'PICK_PLACE' in text
    assert 'e2' in text and 'e4' in text


def test_base_executor_is_abstract():
    """The base Executor.execute is not implemented."""
    with pytest.raises(NotImplementedError):
        Executor().execute([])
