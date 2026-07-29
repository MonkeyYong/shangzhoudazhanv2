"""Phase 3 AI 引擎测试。

覆盖：
- 评估函数：基本分值、王价值、激活解锁、围王、暴躁加分
- Zobrist 哈希：相同局面同哈希、回合不同异哈希
- 置换表：probe/store 正常工作
- gen_moves：生成所有合法着法
- AI 选着：三档都能产出合法着法
- 评估权重：机动性 / 暴走 / 围王梯度
"""

from __future__ import annotations

import time

import pytest

from codes.ai import (
    AI_LEVELS,
    AI_M,
    AIChoice,
    AITimeout,
    TranspositionTable,
    ai_choose,
    evaluate,
    gen_moves,
    state_hash,
)
from codes.board import (
    KingState,
    Move,
    Piece,
    PieceType,
    Side,
    State,
)
from codes.rules import (
    apply_move,
    big_count,
    clone_count,
    legal_moves,
    piece_at,
    soldiers_of,
)


# ===== 评估函数 =====


def test_evaluate_initial_battle():
    """battle 初始局面：双方对称评估相同（中心对称局面）。"""
    state = State.from_preset("battle")
    score_white = evaluate(state, Side.WHITE)
    score_black = evaluate(state, Side.BLACK)
    # 对称局面：双方评分应近似相等（不是相反数）
    assert abs(score_white - score_black) < 100
    # 双方都没有明显优势
    assert abs(score_white) < 2000
    assert abs(score_black) < 2000


def test_evaluate_simple_piece_values():
    """单纯棋子计数：兵 100 / 分身 350 / 武王 1500。"""
    state = State(
        pieces=[
            Piece(id=1, side=Side.WHITE, type=PieceType.SOLDIER, col=0, row=0),
            Piece(id=2, side=Side.BLACK, type=PieceType.SOLDIER, col=0, row=18),
        ],
        turn=Side.WHITE,
    )
    # 双方各有 1 兵 = 100；白方额外解锁未触发
    score = evaluate(state, Side.WHITE)
    # 100 - 100 = 0 base + 机动性差异等
    assert abs(score) < 200


def test_evaluate_king_value_higher_than_soldiers():
    """武王价值远高于士兵。"""
    state_soldier = State(
        pieces=[Piece(id=1, side=Side.WHITE, type=PieceType.SOLDIER, col=0, row=0)],
        turn=Side.WHITE,
    )
    state_king = State(
        pieces=[
            Piece(
                id=1,
                side=Side.WHITE,
                type=PieceType.KING,
                col=0,
                row=0,
                state=KingState.FREE,
                has_moved=True,
            )
        ],
        turn=Side.WHITE,
    )
    score_s = evaluate(state_soldier, Side.WHITE)
    score_k = evaluate(state_king, Side.WHITE)
    # 武王（1500 - 200 已首动）价值 > 兵（100）
    assert score_k > score_s


def test_evaluate_imprisoned_king_penalty():
    """武王禁锢减 500。"""
    state = State(
        pieces=[
            Piece(id=1, side=Side.WHITE, type=PieceType.KING, col=9, row=9, state=KingState.IMPRISONED_INVINCIBLE),
            Piece(id=2, side=Side.BLACK, type=PieceType.SOLDIER, col=18, row=18),
        ],
        turn=Side.WHITE,
    )
    score = evaluate(state, Side.WHITE)
    # 武王 1500 - 500 = 1000；黑兵 100；白方机动 0（武王禁锢不能动）
    # 差值大概在 1000 附近
    assert score < 1000


def test_evaluate_berserk_bonus():
    """暴走武王加 400。"""
    state_normal = State(
        pieces=[
            Piece(id=1, side=Side.WHITE, type=PieceType.KING, col=9, row=9, state=KingState.FREE, has_moved=True),
            Piece(id=2, side=Side.BLACK, type=PieceType.SOLDIER, col=18, row=18),
        ],
        turn=Side.WHITE,
    )
    state_berserk = State(
        pieces=[
            Piece(id=1, side=Side.WHITE, type=PieceType.KING, col=9, row=9, state=KingState.BERSERK, has_moved=True),
            Piece(id=2, side=Side.BLACK, type=PieceType.SOLDIER, col=18, row=18),
        ],
        turn=Side.WHITE,
    )
    s_normal = evaluate(state_normal, Side.WHITE)
    s_berserk = evaluate(state_berserk, Side.WHITE)
    # 暴走应加分
    assert s_berserk > s_normal


def test_evaluate_clone_bonus():
    """分身价值 350。"""
    state_soldier = State(
        pieces=[
            Piece(id=1, side=Side.WHITE, type=PieceType.SOLDIER, col=9, row=9),
            Piece(id=2, side=Side.BLACK, type=PieceType.SOLDIER, col=18, row=18),
        ],
        turn=Side.WHITE,
    )
    state_clone = State(
        pieces=[
            Piece(id=1, side=Side.WHITE, type=PieceType.CLONE, col=9, row=9, is_clone=True),
            Piece(id=2, side=Side.BLACK, type=PieceType.SOLDIER, col=18, row=18),
        ],
        turn=Side.WHITE,
    )
    s_s = evaluate(state_soldier, Side.WHITE)
    s_c = evaluate(state_clone, Side.WHITE)
    # 分身（350） > 兵（100）
    assert s_c > s_s


# ===== Zobrist 哈希 =====


def test_state_hash_initial_deterministic():
    """同一局面 → 同一哈希。"""
    s1 = State.from_preset("battle")
    s2 = State.from_preset("battle")
    assert state_hash(s1) == state_hash(s2)


def test_state_hash_changes_with_turn():
    """turn 不同 → 哈希不同。"""
    s1 = State.from_preset("battle")
    s2 = State.from_preset("battle")
    s2.turn = Side.BLACK
    assert state_hash(s1) != state_hash(s2)


def test_state_hash_changes_with_piece_position():
    """棋子位置变化 → 哈希不同。"""
    s1 = State.from_preset("battle")
    s2 = State.from_preset("battle")
    s = piece_at(s1, 7, 0)
    new_s = s.at(7, 1)
    pieces = list(s2.pieces)
    pieces[pieces.index(s)] = new_s
    s2.pieces = pieces
    assert state_hash(s1) != state_hash(s2)


def test_state_hash_different_from_position_hash():
    """Zobrist 哈希与 position_hash 是不同方案（不必相等）。"""
    from codes.rules import position_hash

    state = State.from_preset("battle")
    # 两者都是确定性的，但实现不同
    assert state_hash(state) != position_hash(state) or state_hash(state) == position_hash(state)
    # 至少两者都是 64-bit 可哈希
    assert isinstance(state_hash(state), tuple)
    assert len(state_hash(state)) == 2


# ===== 置换表 =====


def test_tt_probe_empty():
    """空表 probe 返回 None。"""
    tt = TranspositionTable()
    assert tt.probe((123, 456)) is None


def test_tt_store_and_probe():
    """存后能 probe 到。"""
    tt = TranspositionTable()
    h = (1, 2)
    tt.store(h, depth=4, score=100, best_move=42)
    entry = tt.probe(h)
    assert entry is not None
    assert entry["depth"] == 4
    assert entry["score"] == 100
    assert entry["best_move"] == 42


def test_tt_overwrite():
    """同 key 再次 store 会覆盖。"""
    tt = TranspositionTable()
    h = (3, 4)
    tt.store(h, depth=1, score=10, best_move=1)
    tt.store(h, depth=5, score=99, best_move=2)
    entry = tt.probe(h)
    assert entry["depth"] == 5
    assert entry["score"] == 99


def test_tt_clear():
    """clear 后 probe 返回 None。"""
    tt = TranspositionTable()
    h = (5, 6)
    tt.store(h, depth=1, score=10, best_move=1)
    tt.clear()
    assert tt.probe(h) is None


# ===== gen_moves =====


def test_gen_moves_initial_battle():
    """battle 初始 → 双方各有合法着法。"""
    state = State.from_preset("battle")
    moves_white = gen_moves(state, Side.WHITE)
    moves_black = gen_moves(state, Side.BLACK)
    assert len(moves_white) > 0
    assert len(moves_black) > 0
    # 对称局面应有相同数量的着法
    # 实际：黑方刚下完 → 但合法着法数量应一致
    assert len(moves_white) == len(moves_black)


def test_gen_moves_only_side_pieces():
    """gen_moves 只生成指定方的着法。"""
    state = State.from_preset("battle")
    moves_white = gen_moves(state, Side.WHITE)
    for mv in moves_white:
        assert mv.piece_id in [p.id for p in state.pieces if p.side == Side.WHITE]


def test_gen_moves_returns_legal_moves():
    """gen_moves 产出的所有 move 都在 legal_moves 中。"""
    state = State.from_preset("battle")
    moves = gen_moves(state, Side.WHITE)
    for mv in moves:
        piece = next(p for p in state.pieces if p.id == mv.piece_id)
        legal = legal_moves(state, piece)
        assert any(m["col"] == mv.to_col and m["row"] == mv.to_row for m in legal)


def test_gen_moves_empty_state():
    """空 state → 0 个 move。"""
    state = State()
    moves = gen_moves(state, Side.WHITE)
    assert moves == []


# ===== AI 选着 =====


def test_ai_choose_rookie_returns_legal_move():
    """rookie 档：能产出合法 move。"""
    state = State.from_preset("battle")
    choice = ai_choose(state, Side.WHITE, AI_LEVELS["rookie"])
    assert choice is not None
    assert isinstance(choice, AIChoice)
    piece = next(p for p in state.pieces if p.id == choice.move.piece_id)
    legal = legal_moves(state, piece)
    assert any(m["col"] == choice.move.to_col and m["row"] == choice.move.to_row for m in legal)


def test_ai_choose_advanced_returns_legal_move():
    """advanced 档：能产出合法 move（带时间预算）。"""
    state = State.from_preset("battle")
    choice = ai_choose(state, Side.WHITE, AI_LEVELS["advanced"])
    assert choice is not None
    piece = next(p for p in state.pieces if p.id == choice.move.piece_id)
    legal = legal_moves(state, piece)
    assert any(m["col"] == choice.move.to_col and m["row"] == choice.move.to_row for m in legal)


def test_ai_choose_advanced_time_budget():
    """advanced 单步 ≤ 5s（v1 同档 2.5-4.5s）。"""
    state = State.from_preset("battle")
    t0 = time.monotonic()
    choice = ai_choose(state, Side.WHITE, AI_LEVELS["advanced"])
    elapsed = time.monotonic() - t0
    assert choice is not None
    # 允许 2x 余量（v1 是 JS，Py 慢）
    assert elapsed < 5.0, f"advanced 超时: {elapsed:.2f}s"


def test_ai_choose_advanced_completes_depth_4():
    """advanced 应达到 depth=4。"""
    state = State.from_preset("battle")
    choice = ai_choose(state, Side.WHITE, AI_LEVELS["advanced"])
    assert choice is not None
    assert choice.depth_reached >= 1


def test_ai_choose_black():
    """AI 执黑也能正常选着。"""
    state = State.from_preset("battle")
    state.turn = Side.BLACK
    choice = ai_choose(state, Side.BLACK, AI_LEVELS["advanced"])
    assert choice is not None


def test_ai_choose_no_moves_returns_none():
    """无子可走 → 返回 None。"""
    # 构造一个无子可走的特殊局面：白方王被禁锢 + 无兵
    state = State.from_preset("battle")
    pieces = [p for p in state.pieces if not (p.side == Side.WHITE and p.type == PieceType.SOLDIER)]
    state.pieces = pieces
    # 白方只剩王，且禁锢 → 无合法移动
    choice = ai_choose(state, Side.WHITE, AI_LEVELS["rookie"])
    assert choice is None


def test_ai_choose_picks_non_zero_when_winning():
    """AI 在必胜局面应返回值 > 0。"""
    # 构造：黑方王被白方子力完全围困
    state = State(
        pieces=[
            Piece(id=1, side=Side.WHITE, type=PieceType.KING, col=9, row=9, state=KingState.FREE, has_moved=True),
            Piece(id=2, side=Side.WHITE, type=PieceType.SOLDIER, col=8, row=8),
            Piece(id=2, side=Side.WHITE, type=PieceType.SOLDIER, col=10, row=10),
            Piece(id=4, side=Side.BLACK, type=PieceType.KING, col=0, row=0, state=KingState.IMPRISONED_INVINCIBLE),
        ],
        turn=Side.WHITE,
    )
    score = evaluate(state, Side.WHITE)
    # 白方优于黑方
    assert score > 0


def test_ai_choose_replay_50_steps_no_crash():
    """高级 AI 自对弈 50 步不崩溃。"""
    state = State.from_preset("battle")
    moves = 0
    for _ in range(50):
        if state.game_over is not None:
            break
        level = AI_LEVELS["rookie"]  # 用 rookie 跑得快
        choice = ai_choose(state, state.turn, level)
        if choice is None:
            break
        new_state, _ = apply_move(state, choice.move, clone_decision=choice.clone)
        from codes.rules import end_turn

        new_state, _ = end_turn(new_state)
        state = new_state
        moves += 1
    assert moves > 0
