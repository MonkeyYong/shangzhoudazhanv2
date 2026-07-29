"""商周大战 v2 · Python 核心引擎

按 docs/v2-architecture.md 设计：
- board.py   数据层：常量 + Piece + State + Move
- rules.py   规则层：移动 / 吃子 / 禁锢 / 分身 / 暴走 / 胜负
- ai.py      AI 引擎：Negamax + α-β + Zobrist + 置换表
- presets.py 3 档开局（14/22/34 子）
- replay.py  棋谱 record + JSON 序列化
"""

from codes.board import (
    SIZE,
    COLS,
    COL_LETTERS,
    WHITE_PALACE,
    BLACK_PALACE,
    Side,
    PieceType,
    KingState,
    Piece,
    State,
    Move,
    in_palace,
    coord_to_str,
    str_to_coord,
)
from codes.presets import PRESETS, build_layout

__all__ = [
    "SIZE",
    "COLS",
    "COL_LETTERS",
    "WHITE_PALACE",
    "BLACK_PALACE",
    "Side",
    "PieceType",
    "KingState",
    "Piece",
    "State",
    "Move",
    "in_palace",
    "coord_to_str",
    "str_to_coord",
    "PRESETS",
    "build_layout",
]
