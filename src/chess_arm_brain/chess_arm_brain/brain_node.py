"""Thin rclpy node wrapping :mod:`chess_arm_brain.brain`.

Exposes the three canonical brain services from ``chess_arm_interfaces``:

* ``ResolveHumanMove`` — changed squares -> uci/san of the human's move
  (resolves it and pushes it onto the authoritative board).
* ``GetEngineMove``    — ask Stockfish for the reply, push it, report result.
* ``PlanPieceActions`` — decompose a uci move into ``PieceAction[]`` with
  world coordinates filled in from ``board_coordinates.yaml``.

All real game logic lives in the pure-Python library; this file only marshals
between ROS messages and that library.
"""

from __future__ import annotations

import chess
import rclpy
from geometry_msgs.msg import Point
from rclpy.node import Node

from chess_arm_interfaces.msg import PieceAction
from chess_arm_interfaces.srv import (
    DetectChanges,
    GetEngineMove,
    PlanPieceActions,
    ResolveHumanMove,
)

from chess_arm_brain.brain import BoardCoordinates, ChessBrain, StockfishEngine


class BrainNode(Node):
    def __init__(self):
        super().__init__("chess_arm_brain")

        # --- parameters ----------------------------------------------------
        self.declare_parameter("movetime_ms", 1000)
        self.declare_parameter("skill_level", -1)  # -1 => unset
        self.declare_parameter("elo", -1)  # -1 => unset
        self.declare_parameter("lift_z", -1.0)  # <0 => use coords.lift_z

        movetime_ms = int(self.get_parameter("movetime_ms").value)
        skill = int(self.get_parameter("skill_level").value)
        elo = int(self.get_parameter("elo").value)

        engine = StockfishEngine(
            skill_level=(skill if skill >= 0 else None),
            elo=(elo if elo >= 0 else None),
            movetime_ms=movetime_ms,
        )

        # --- coordinates (from chess_arm_description share) ----------------
        try:
            coords = BoardCoordinates.from_package_share()
        except Exception as exc:  # pragma: no cover - depends on install layout
            self.get_logger().error(
                f"failed to load board_coordinates.yaml: {exc}; "
                "PlanPieceActions xyz fields will be empty"
            )
            coords = None

        self.brain = ChessBrain(coordinates=coords, engine=engine)

        # --- services ------------------------------------------------------
        self.create_service(
            ResolveHumanMove, "resolve_human_move", self._on_resolve_human_move
        )
        self.create_service(GetEngineMove, "get_engine_move", self._on_get_engine_move)
        self.create_service(
            PlanPieceActions, "plan_piece_actions", self._on_plan_piece_actions
        )

        self.get_logger().info(
            "chess_arm_brain ready (movetime=%dms, skill=%s, elo=%s, coords=%s)"
            % (
                movetime_ms,
                skill if skill >= 0 else "default",
                elo if elo >= 0 else "default",
                "loaded" if coords is not None else "MISSING",
            )
        )

    # -- ResolveHumanMove ---------------------------------------------------
    def _on_resolve_human_move(self, request, response):
        changed = list(request.changed_squares)
        try:
            move = self.brain.resolve_human_move(changed)
        except Exception as exc:  # pragma: no cover - defensive
            response.ok = False
            response.uci = ""
            response.san = ""
            response.message = f"error resolving move: {exc}"
            return response

        if move is None:
            response.ok = False
            response.uci = ""
            response.san = ""
            response.message = (
                f"could not resolve a unique legal move from changed squares "
                f"{changed} (ambiguous or illegal)"
            )
            return response

        san = self.brain.board.san(move)
        self.brain.push(move)
        response.ok = True
        response.uci = move.uci()
        response.san = san
        response.message = ""
        self.get_logger().info(f"human move resolved: {san} ({move.uci()})")
        return response

    # -- GetEngineMove ------------------------------------------------------
    def _on_get_engine_move(self, request, response):
        if self.brain.is_game_over():
            response.ok = False
            response.uci = ""
            response.san = ""
            response.game_over = True
            response.result = self.brain.result()
            response.fen = self.brain.fen
            response.message = "game already over" if hasattr(response, "message") else ""
            return response

        try:
            move = self.brain.engine_move()
        except Exception as exc:
            response.ok = False
            response.uci = ""
            response.san = ""
            response.game_over = False
            response.result = "*"
            response.fen = self.brain.fen
            self.get_logger().error(f"engine error: {exc}")
            return response

        # Compute SAN + the post-move status WITHOUT advancing the authoritative
        # board: PlanPieceActions decomposes this move on the PRE-move board and
        # only THEN pushes it. (If we pushed here, the later decompose would see
        # the move as already played and reject it as illegal.)
        san = self.brain.board.san(move)
        self.brain.board.push(move)
        try:
            game_over = self.brain.board.is_game_over()
            result = self.brain.board.result() if game_over else "*"
            fen = self.brain.board.fen()
        finally:
            self.brain.board.pop()
        response.ok = True
        response.uci = move.uci()
        response.san = san
        response.game_over = game_over
        response.result = result
        response.fen = fen
        self.get_logger().info(f"engine move (peek, pushed by PlanPieceActions): {san} ({move.uci()})")
        return response

    # -- PlanPieceActions ---------------------------------------------------
    def _on_plan_piece_actions(self, request, response):
        uci = request.uci
        try:
            move = chess.Move.from_uci(uci)
        except Exception as exc:
            response.ok = False
            response.actions = []
            response.message = f"bad uci '{uci}': {exc}"
            return response

        try:
            raw = self.brain.decompose(move)
        except Exception as exc:
            response.ok = False
            response.actions = []
            response.message = f"cannot plan actions for {uci}: {exc}"
            return response

        # Decompose succeeded on the PRE-move board; NOW advance the
        # authoritative game state by playing the move (GetEngineMove only
        # peeked it). This keeps the engine board, the arm plan, and the
        # /sim_board_fen ground truth in lock-step.
        try:
            self.brain.push(move)
        except Exception as exc:
            response.ok = False
            response.actions = []
            response.message = f"cannot push {uci} after decompose: {exc}"
            return response

        actions = []
        coords = self.brain.coords
        for a in raw:
            msg = PieceAction()
            msg.action_type = int(a["action_type"])
            msg.from_square = a["from_square"]
            msg.to_square = a["to_square"]
            msg.piece = a.get("piece", "")
            if coords is not None:
                msg.from_xyz = self._point(coords, a["from_square"], coords.grasp_z)
                msg.to_xyz = self._point(coords, a["to_square"], coords.grasp_z)
            actions.append(msg)

        response.ok = True
        response.actions = actions
        response.message = ""
        return response

    @staticmethod
    def _point(coords: BoardCoordinates, name: str, z: float) -> Point:
        p = Point()
        if coords.has(name):
            x, y, zz = coords.xyz(name, z)
            p.x, p.y, p.z = float(x), float(y), float(zz)
        return p


def main(args=None):
    rclpy.init(args=args)
    node = BrainNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            node.brain.engine.close()
        except Exception:
            pass
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
