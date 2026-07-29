"""数据层：常量 + Piece + State + Move

权威来源：v1 codes/商周大战.html (lines 487-502, 1164-1240)
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Optional


# ===== 棋盘常量 =====

SIZE = 19
"""棋盘边长；列 0..18，行 0..18。"""

COL_LETTERS = "ABCDEFGHJKLMNOPQRST"
"""列字母映射（跳过 I）；col 0 → 'A', col 18 → 'T'。"""

COLS = COL_LETTERS
""":data:`COL_LETTERS` 的别名。"""

# 王城定义：(c0, c1, r0, r1) 闭区间
WHITE_PALACE = (7, 11, 0, 3)
"""白方王城：H-M / 行 1-4（内部 0-base：row 0..3）。黑方武王开局位 K1 在此。"""

BLACK_PALACE = (7, 11, 15, 18)
"""黑方王城：H-M / 行 16-19（内部 0-base：row 15..18）。白方武王开局位 K19 在此。"""

# ===== 枚举 =====


class Side(str, Enum):
    """双方阵营。str 混入以便 JSON 序列化时直接得到 "white"/"black"。"""

    WHITE = "white"
    BLACK = "black"

    @property
    def opposite(self) -> "Side":
        return Side.BLACK if self is Side.WHITE else Side.WHITE


class PieceType(str, Enum):
    """棋子类型。"""

    KING = "king"
    SOLDIER = "soldier"
    CLONE = "clone"


class KingState(str, Enum):
    """武王状态机。"""

    IMPRISONED_INVINCIBLE = "imprisoned_invincible"
    """初始无敌禁锢（被 ≥2 敌子在 2 格吃子距离围困）。"""

    FREE = "free"
    """自由态（解禁后或从未被围困）。"""

    BERSERK = "berserk"
    """暴走（踏入己方王城）；射线无限、可被吃。"""


# ===== Move 数据结构 =====


@dataclass(frozen=True)
class Move:
    """一步棋的最基本信息（不含历史/克隆决策等）。"""

    piece_id: int
    from_col: int
    from_row: int
    to_col: int
    to_row: int
    capture: bool = False
    """是否吃子。"""
    clone: bool = False
    """是否触发分身（仅在兵 ↔ 武王互入范围时）。"""


# ===== Piece 数据结构 =====


@dataclass(frozen=True)
class Piece:
    """单枚棋子；frozen=True 保证不可变，移动 / 吃子时通过 replace() 生成新实例。"""

    id: int
    side: Side
    type: PieceType
    col: int
    row: int
    state: KingState = KingState.FREE
    is_clone: bool = False
    has_moved: bool = False
    """武王是否已移动（决定是否解锁分身能力 + 解除无敌）。"""
    actively_unlocked: bool = False
    """(武王专属) 是否被己方兵主动解锁过一次。"""
    dead: bool = False

    def at(self, col: int, row: int) -> "Piece":
        """返回位置更新后的新 Piece（其他字段不变）。"""
        return replace(self, col=col, row=row)

    def with_state(self, state: KingState) -> "Piece":
        return replace(self, state=state)

    def mark_moved(self) -> "Piece":
        return replace(self, has_moved=True)

    def mark_dead(self) -> "Piece":
        return replace(self, dead=True)


# ===== State 数据结构 =====


@dataclass
class State:
    """完整局面状态。设计原则：v2 规则层纯函数化（apply_move 返回新 State）。

    State 本身可变（apply_move 内部先 clone 再 mutate），但外部应通过 apply_move
    改变局势，永不直接修改 state.pieces / state.turn。
    """

    pieces: list[Piece] = field(default_factory=list)
    turn: Side = Side.WHITE
    side_lost_clone: dict[Side, bool] = field(
        default_factory=lambda: {Side.WHITE: False, Side.BLACK: False}
    )
    """暴走后己方失去分身能力。"""
    side_clone_unlocked: dict[Side, bool] = field(
        default_factory=lambda: {Side.WHITE: False, Side.BLACK: False}
    )
    """武王首次移动（解锁分身能力）后锁定。"""
    step_count: int = 0
    game_over: Optional[dict] = None
    """None / {"winner": "white"|"black"|"draw", "reason": str}"""

    # ----- 构造 -----

    @classmethod
    def from_preset(cls, name: str) -> "State":
        """从预设档位构造初始局面（piece.id 从 1 起）。"""
        from codes.presets import build_layout

        layout = build_layout(name)
        next_id = 1
        pieces: list[Piece] = []
        for side, ptype, col, row in layout:
            pieces.append(
                Piece(
                    id=next_id,
                    side=Side(side),
                    type=PieceType(ptype),
                    col=col,
                    row=row,
                    state=KingState.IMPRISONED_INVINCIBLE
                    if ptype == "king"
                    else KingState.FREE,
                )
            )
            next_id += 1
        return cls(pieces=pieces, turn=Side.WHITE)

    @classmethod
    def from_dict(cls, d: dict) -> "State":
        """从 JSON 字典反序列化（与 to_dict 配套）。"""
        pieces = [
            Piece(
                id=p["id"],
                side=Side(p["side"]),
                type=PieceType(p["type"]),
                col=p["col"],
                row=p["row"],
                state=KingState(p.get("state", "free")),
                is_clone=p.get("is_clone", False),
                has_moved=p.get("has_moved", False),
                actively_unlocked=p.get("actively_unlocked", False),
                dead=p.get("dead", False),
            )
            for p in d.get("pieces", [])
        ]
        return cls(
            pieces=pieces,
            turn=Side(d.get("turn", "white")),
            side_lost_clone={
                Side.WHITE: d.get("side_lost_clone", {}).get("white", False),
                Side.BLACK: d.get("side_lost_clone", {}).get("black", False),
            },
            side_clone_unlocked={
                Side.WHITE: d.get("side_clone_unlocked", {}).get("white", False),
                Side.BLACK: d.get("side_clone_unlocked", {}).get("black", False),
            },
            step_count=d.get("step_count", 0),
            game_over=d.get("game_over"),
        )

    def to_dict(self) -> dict:
        """序列化为 JSON 字典（与 from_dict 配套）。"""
        return {
            "pieces": [
                {
                    "id": p.id,
                    "side": p.side.value,
                    "type": p.type.value,
                    "col": p.col,
                    "row": p.row,
                    "state": p.state.value,
                    "is_clone": p.is_clone,
                    "has_moved": p.has_moved,
                    "actively_unlocked": p.actively_unlocked,
                    "dead": p.dead,
                }
                for p in self.pieces
            ],
            "turn": self.turn.value,
            "side_lost_clone": {s.value: v for s, v in self.side_lost_clone.items()},
            "side_clone_unlocked": {s.value: v for s, v in self.side_clone_unlocked.items()},
            "step_count": self.step_count,
            "game_over": self.game_over,
        }

    def clone(self) -> "State":
        """深拷贝（pieces 各自是 frozen dataclass，浅拷贝即可）。"""
        return State(
            pieces=list(self.pieces),  # Piece 是 frozen，共享引用安全
            turn=self.turn,
            side_lost_clone=dict(self.side_lost_clone),
            side_clone_unlocked=dict(self.side_clone_unlocked),
            step_count=self.step_count,
            game_over=self.game_over,
        )


# ===== 坐标辅助 =====


def coord_to_str(col: int, row: int) -> str:
    """(col, row) 0-base → 围棋坐标 'K10'。"""
    return COL_LETTERS[col] + str(row + 1)


def str_to_coord(s: str) -> tuple[int, int]:
    """'K10' → (col=9, row=9)。"""
    s = s.strip().upper()
    if len(s) < 2:
        raise ValueError(f"坐标格式错误: {s!r}")
    col = COL_LETTERS.index(s[0])
    row = int(s[1:]) - 1
    return col, row


def in_palace(side: Side, col: int, row: int) -> bool:
    """判断 (col, row) 是否在 side 方的王城内。"""
    c0, c1, r0, r1 = WHITE_PALACE if side is Side.WHITE else BLACK_PALACE
    return c0 <= col <= c1 and r0 <= row <= r1
