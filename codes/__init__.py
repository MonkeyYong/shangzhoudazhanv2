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
from codes.rules import (
    DIRS_8,
    piece_at,
    king_of,
    big_count,
    clone_count,
    soldiers_of,
    reachable_cells,
    legal_moves,
    theoretical_range,
    is_imprisoned,
    recompute_king_states,
    active_unlock_check,
    berserk_check,
    in_any_friendly_big_range,
    clone_offer_check,
    perform_clone,
    side_unlocked,
    check_win_loss,
    has_any_move,
    position_hash,
    apply_move,
    end_turn,
)
from codes.ai import (
    AILevel,
    AI_LEVELS,
    AIChoice,
    AI_M,
    AITimeout,
    TranspositionTable,
    evaluate,
    gen_moves,
    state_hash,
    ai_choose,
)
from codes.replay import Record, move_to_notation, record_to_text

__all__ = [
    # 棋盘常量
    "SIZE",
    "COLS",
    "COL_LETTERS",
    "WHITE_PALACE",
    "BLACK_PALACE",
    # 枚举与数据类
    "Side",
    "PieceType",
    "KingState",
    "Piece",
    "State",
    "Move",
    # 辅助函数
    "in_palace",
    "coord_to_str",
    "str_to_coord",
    # 预设
    "PRESETS",
    "build_layout",
    # 规则层
    "DIRS_8",
    "piece_at",
    "king_of",
    "big_count",
    "clone_count",
    "soldiers_of",
    "reachable_cells",
    "legal_moves",
    "theoretical_range",
    "is_imprisoned",
    "recompute_king_states",
    "active_unlock_check",
    "berserk_check",
    "in_any_friendly_big_range",
    "clone_offer_check",
    "perform_clone",
    "side_unlocked",
    "check_win_loss",
    "has_any_move",
    "position_hash",
    "apply_move",
    "end_turn",
    # AI 引擎
    "AILevel",
    "AI_LEVELS",
    "AIChoice",
    "AI_M",
    "AITimeout",
    "TranspositionTable",
    "evaluate",
    "gen_moves",
    "state_hash",
    "ai_choose",
    # 棋谱
    "Record",
    "move_to_notation",
    "record_to_text",
]
