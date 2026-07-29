"""Phase 2 规则层测试。

覆盖：
- 基础查询：piece_at / king_of / big_count / clone_count / soldiers_of
- 移动：reachable_cells / legal_moves（普通路径 / 阻挡 / 吃子 / 暴走射线 / 禁锢不动）
- 武王状态：theoretical_range / is_imprisoned / recompute_king_states
- 主动解锁
- 暴走（含对方解禁副作用）
- 分身：clone_offer_check / perform_clone
- 胜负：check_win_loss / has_any_move（停棋 / 灭子 / 禁锢无兵）
- 局面哈希
- apply_move 完整流程
- end_turn（含平局循环检测）
"""

from __future__ import annotations

import pytest

from codes.board import (
    KingState,
    Move,
    Piece,
    PieceType,
    Side,
    State,
)
from codes.rules import (
    DIRS_8,
    active_unlock_check,
    apply_move,
    berserk_check,
    big_count,
    check_win_loss,
    clone_count,
    clone_offer_check,
    end_turn,
    has_any_move,
    in_any_friendly_big_range,
    is_imprisoned,
    king_of,
    legal_moves,
    perform_clone,
    piece_at,
    position_hash,
    reachable_cells,
    recompute_king_states,
    side_unlocked,
    soldiers_of,
    theoretical_range,
)


# ===== 基础查询 =====


def test_piece_at_found():
    state = State.from_preset("battle")
    p = piece_at(state, 9, 18)  # 白武王 K19
    assert p is not None
    assert p.side == Side.WHITE
    assert p.type == PieceType.KING


def test_piece_at_empty():
    state = State.from_preset("battle")
    assert piece_at(state, 0, 0) is None  # A1 空格


def test_king_of():
    state = State.from_preset("battle")
    assert king_of(state, Side.WHITE).col == 9 and king_of(state, Side.WHITE).row == 18
    assert king_of(state, Side.BLACK).col == 9 and king_of(state, Side.BLACK).row == 0


def test_big_count_battle():
    state = State.from_preset("battle")
    assert big_count(state, Side.WHITE) == 1  # 1 武王
    assert big_count(state, Side.BLACK) == 1


def test_soldiers_of_battle():
    state = State.from_preset("battle")
    assert soldiers_of(state, Side.WHITE) == 10  # 22 - 2 王 = 20 兵 / 2 = 10
    assert soldiers_of(state, Side.BLACK) == 10


def test_clone_count_initial_zero():
    state = State.from_preset("battle")
    assert clone_count(state, Side.WHITE) == 0
    assert clone_count(state, Side.BLACK) == 0


# ===== reachable_cells / legal_moves =====


def test_reachable_imprisoned_returns_empty():
    """禁锢武王不能动。"""
    state = State.from_preset("battle")
    w_king = king_of(state, Side.WHITE)
    assert w_king.state == KingState.IMPRISONED_INVINCIBLE
    assert reachable_cells(state, w_king) == []


def test_reachable_soldier_2_cells_normal():
    """普通士兵：8 方向 × 2 格 = 最多 16 格（无阻挡时）。"""
    state = State.from_preset("battle")
    # 找白方一个没在边角的士兵：F6 (5, 5)
    # 但 8 方向中有 2 格被己方兵挡住（H4 (7,3) → 阻 SE；H8 (7,7) → 阻 NE）
    # 所以总可达数为 14
    s = piece_at(state, 5, 5)
    assert s is not None and s.type == PieceType.SOLDIER
    moves = reachable_cells(state, s)
    # 16 减去被己方阻挡损失的 2 格
    assert len(moves) == 14


def test_reachable_soldier_alone_max_16():
    """构造只有单兵的局面 → 8×2=16 全可达。"""
    state = State(
        pieces=[Piece(id=1, side=Side.WHITE, type=PieceType.SOLDIER, col=9, row=9)],
        turn=Side.WHITE,
    )
    moves = reachable_cells(state, state.pieces[0])
    assert len(moves) == 16


def test_reachable_capture_stops():
    """吃敌后停。"""
    state = State(
        pieces=[
            Piece(id=1, side=Side.WHITE, type=PieceType.SOLDIER, col=9, row=9),
            Piece(id=2, side=Side.BLACK, type=PieceType.SOLDIER, col=9, row=11),  # 距白兵 2 格
        ],
        turn=Side.WHITE,
    )
    moves = reachable_cells(state, state.pieces[0])
    # 北 1 格 (9, 10) 空
    assert {"col": 9, "row": 10, "capture": False} in moves
    # 北 2 格 (9, 11) 吃黑兵
    assert {"col": 9, "row": 11, "capture": True} in moves
    # 北 3 格 (9, 12) 不可达（吃子后停）
    assert not any(m["col"] == 9 and m["row"] == 12 for m in moves)


def test_reachable_blocked_by_enemy_stops():
    """路径不穿敌，吃敌后停。"""
    state = State.from_preset("battle")
    # 白方 H1 (7, 0) 向上是 H2 (7, 1)（空）、H3 (7, 2)（空）、H4 (7, 3）= H4 有己方兵
    s = piece_at(state, 7, 0)  # H1 白方兵
    moves = reachable_cells(state, s)
    # 验证：向上 2 格 (7, 2) = H3 应可达（穿过 H2 空 + H3 空）
    assert {"col": 7, "row": 2, "capture": False} in moves
    # 验证：不能到 H4 (7, 3) = 己方兵阻挡
    assert not any(m["col"] == 7 and m["row"] == 3 for m in moves)


def test_reachable_boundary():
    """出界即停。"""
    state = State.from_preset("battle")
    # 构造一个 state：白方兵在 (0, 0)
    p = Piece(id=99, side=Side.WHITE, type=PieceType.SOLDIER, col=0, row=0)
    state.pieces.append(p)
    moves = reachable_cells(state, p)
    # 验证：所有 move 的 col >= 0, row >= 0
    for m in moves:
        assert m["col"] >= 0 and m["row"] >= 0
    # 验证：向右 1 格 (1, 0) 可达
    assert {"col": 1, "row": 0, "capture": False} in moves
    # 验证：向右 2 格 (2, 0) 可达
    assert {"col": 2, "row": 0, "capture": False} in moves


def test_legal_moves_filters_invincible_king():
    """legal_moves 过滤掉 has_moved=False 的武王（不可被吃）。"""
    state = State.from_preset("battle")
    s = piece_at(state, 7, 0)  # H1 白方兵
    moves = legal_moves(state, s)
    # 验证：不能吃 (9, 0) 的武王（has_moved=False）
    assert not any(m["col"] == 9 and m["row"] == 0 for m in moves)


def test_legal_moves_allows_capturing_moved_king():
    """has_moved=True 的武王可被吃。"""
    state = State.from_preset("battle")
    b_king = king_of(state, Side.BLACK)
    new_b_king = b_king.mark_moved()
    pieces = list(state.pieces)
    pieces[pieces.index(b_king)] = new_b_king
    state.pieces = pieces
    s = piece_at(state, 7, 0)
    moves = legal_moves(state, s)
    # 验证：可以吃 (9, 0) 的武王
    assert {"col": 9, "row": 0, "capture": True} in moves


def test_reachable_berserk_ray():
    """暴走武王射线无限。"""
    # 构造：白武王在 (9, 9) 中心，berserk 态，无其它阻挡
    state = State(
        pieces=[
            Piece(
                id=1,
                side=Side.WHITE,
                type=PieceType.KING,
                col=9,
                row=9,
                state=KingState.BERSERK,
                has_moved=True,
                actively_unlocked=True,
            )
        ],
        turn=Side.WHITE,
    )
    moves = reachable_cells(state, state.pieces[0])
    # 应能到 (0, 9)/（18, 9）/（9, 0）/（9, 18）
    for col, row in [(0, 9), (18, 9), (9, 0), (9, 18)]:
        assert {"col": col, "row": row, "capture": False} in moves


# ===== theoretical_range =====


def test_theoretical_range_2_cells_no_block():
    """普通武王 8 方向 × 2 格（不含阻挡）。"""
    state = State.from_preset("battle")
    w_king = king_of(state, Side.WHITE)
    new_king = w_king.at(9, 9)
    pieces = list(state.pieces)
    pieces[pieces.index(w_king)] = new_king
    state.pieces = pieces
    cells = theoretical_range(state, new_king)
    # 8 方向 × 2 格 = 16 cells
    assert len(cells) == 16
    assert (7, 9) in cells  # 西 2 格
    assert (11, 9) in cells  # 东 2 格
    assert (9, 7) in cells  # 南 2 格
    assert (9, 11) in cells  # 北 2 格
    assert (7, 7) in cells  # 西南
    assert (11, 11) in cells  # 东北


def test_theoretical_range_includes_1_and_2():
    """武王范围包含 1 格和 2 格。"""
    state = State.from_preset("battle")
    w_king = king_of(state, Side.WHITE)
    new_king = w_king.at(9, 9)
    pieces = list(state.pieces)
    pieces[pieces.index(w_king)] = new_king
    state.pieces = pieces
    cells = theoretical_range(state, new_king)
    # 1 格 (8, 9)
    assert (8, 9) in cells
    # 2 格 (7, 9)
    assert (7, 9) in cells


# ===== is_imprisoned / recompute_king_states =====


def test_is_imprisoned_initial_state():
    """battle 档开局：白武王在黑方王城（K19），被黑方 3 兵围困（H19/K17/M19）→ 禁锢。"""
    state = State.from_preset("battle")
    w_king = king_of(state, Side.WHITE)
    assert is_imprisoned(state, w_king) is True


def test_is_imprisoned_false_for_clone():
    """分身不算（不是本体武王）。"""
    state = State.from_preset("battle")
    fake_clone = Piece(id=99, side=Side.WHITE, type=PieceType.CLONE, col=9, row=18, is_clone=True)
    state.pieces.append(fake_clone)
    # 分身返回 False（不是禁锢判定目标）
    assert is_imprisoned(state, fake_clone) is False


def test_recompute_king_states_keeps_imprisoned():
    """未移动的武王被围 → 恢复禁锢。"""
    state = State.from_preset("battle")
    # 初始状态：白武王 = imprisoned_invincible
    w_king = king_of(state, Side.WHITE)
    assert w_king.state == KingState.IMPRISONED_INVINCIBLE
    # recompute 后仍为 imprisoned
    new_state = recompute_king_states(state)
    new_king = next(p for p in new_state.pieces if p.id == w_king.id)
    assert new_king.state == KingState.IMPRISONED_INVINCIBLE


def test_recompute_king_states_releases_moved():
    """has_moved=True 的武王 → 强制 free。"""
    state = State.from_preset("battle")
    w_king = king_of(state, Side.WHITE)
    pieces = list(state.pieces)
    pieces[pieces.index(w_king)] = w_king.mark_moved()
    state.pieces = pieces
    new_state = recompute_king_states(state)
    new_king = next(p for p in new_state.pieces if p.id == w_king.id)
    assert new_king.state == KingState.FREE


def test_recompute_king_states_keeps_berserk():
    """暴走武王不会被重算影响。"""
    state = State.from_preset("battle")
    w_king = king_of(state, Side.WHITE)
    pieces = list(state.pieces)
    pieces[pieces.index(w_king)] = Piece(
        id=w_king.id,
        side=w_king.side,
        type=w_king.type,
        col=w_king.col,
        row=w_king.row,
        state=KingState.BERSERK,
        is_clone=w_king.is_clone,
        has_moved=True,
        actively_unlocked=False,
        dead=False,
    )
    state.pieces = pieces
    new_state = recompute_king_states(state)
    new_king = next(p for p in new_state.pieces if p.id == w_king.id)
    assert new_king.state == KingState.BERSERK


# ===== active_unlock_check =====


def test_active_unlock_when_soldier_in_range():
    """己方兵移入禁锢武王理论范围 → 解除禁锢 + 标记 actively_unlocked。"""
    # 构造：白武王 (9, 17) 禁锢中；白兵移到 (8, 17) → 距 (9, 17) 切比雪夫 1
    state = State(
        pieces=[
            Piece(id=1, side=Side.WHITE, type=PieceType.KING, col=9, row=17, state=KingState.IMPRISONED_INVINCIBLE),
            Piece(id=2, side=Side.WHITE, type=PieceType.SOLDIER, col=8, row=17),
        ],
        turn=Side.WHITE,
    )
    soldier = state.pieces[1]
    new_state = active_unlock_check(state, soldier)
    new_king = next(p for p in new_state.pieces if p.id == 1)
    assert new_king.state == KingState.FREE
    assert new_king.actively_unlocked is True


def test_active_unlock_does_not_affect_enemy_king():
    """移动己方兵不应影响对方武王。"""
    state = State.from_preset("battle")
    s = piece_at(state, 7, 0)
    new_s = s.at(8, 1)
    pieces = list(state.pieces)
    pieces[pieces.index(s)] = new_s
    state.pieces = pieces
    new_state = active_unlock_check(state, new_s)
    # 白武王未动、未接应 → 状态不变
    w_king = king_of(state, Side.WHITE)
    new_w_king = next(p for p in new_state.pieces if p.id == w_king.id)
    assert new_w_king.state == KingState.IMPRISONED_INVINCIBLE


# ===== berserk_check =====


def test_berserk_king_entering_own_palace():
    """武王踏入己方王城 → 暴走 + 己方无分身 + 对方解禁。"""
    # 构造：白武王在 (9, 9) 即将移入白方王城 (9, 2)
    state = State.from_preset("battle")
    w_king = king_of(state, Side.WHITE)
    new_w_king = w_king.at(9, 2).mark_moved()  # (9, 2) 在白方王城
    pieces = list(state.pieces)
    pieces[pieces.index(w_king)] = new_w_king
    state.pieces = pieces
    new_state = berserk_check(state, new_w_king)
    # 白武王应进入 berserk
    final_w_king = next(p for p in new_state.pieces if p.id == w_king.id)
    assert final_w_king.state == KingState.BERSERK
    # side_lost_clone 标记
    assert new_state.side_lost_clone[Side.WHITE] is True
    # 黑武王解禁
    b_king = king_of(state, Side.BLACK)
    final_b_king = next(p for p in new_state.pieces if p.id == b_king.id)
    assert final_b_king.state == KingState.FREE
    assert final_b_king.has_moved is True
    assert final_b_king.actively_unlocked is True


def test_berserk_soldier_does_not_trigger():
    """士兵进入王城不会触发暴走。"""
    state = State(
        pieces=[Piece(id=1, side=Side.WHITE, type=PieceType.SOLDIER, col=8, row=2)],
        turn=Side.WHITE,
    )
    new_state = berserk_check(state, state.pieces[0])
    # 状态应不变
    assert new_state.side_lost_clone[Side.WHITE] is False


# ===== 分身检测 / perform_clone =====


def test_clone_offer_soldier_enter_king_range():
    """己方兵移入己方武王范围 → 触发分身。"""
    # 构造：白武王 (9, 17) 已移动；白兵 (8, 17) 距 (9, 17) 切比雪夫 1
    state = State(
        pieces=[
            Piece(id=1, side=Side.WHITE, type=PieceType.KING, col=9, row=17, state=KingState.FREE, has_moved=True),
            Piece(id=2, side=Side.WHITE, type=PieceType.SOLDIER, col=8, row=17),
        ],
        turn=Side.WHITE,
        side_clone_unlocked={Side.WHITE: True, Side.BLACK: False},
    )
    new_state, candidates = clone_offer_check(state, state.pieces[1])
    assert len(candidates) >= 1
    assert candidates[0].id == 2


def test_clone_offer_disallowed_when_two_bigs():
    """场上已有 2 个大棋子 → 不触发分身。"""
    state = State.from_preset("battle")
    # 构造：白方已有 1 武王 + 1 分身
    w_king = king_of(state, Side.WHITE)
    new_w_king = w_king.at(9, 17).mark_moved()
    pieces = list(state.pieces)
    pieces[pieces.index(w_king)] = new_w_king
    state.pieces = pieces
    # 添加一个白方分身
    fake_clone = Piece(id=99, side=Side.WHITE, type=PieceType.CLONE, col=10, row=10, is_clone=True)
    state.pieces.append(fake_clone)
    # 用黑方兵 (9, 16) 触发（不行，需己方兵）
    # 改用白兵 (8, 16) 也在 (9, 17) 2 格内
    s = piece_at(state, 9, 16)  # 黑兵 → 跳过
    # 重新查找白兵
    s_white = next(p for p in state.pieces if p.side == Side.WHITE and p.type == PieceType.SOLDIER)
    new_state, candidates = clone_offer_check(state, s_white)
    # 白方已有 2 大 → 无候选
    assert candidates == []


def test_clone_offer_disallowed_before_king_moves():
    """武王首次移动前 → 不触发分身（side_clone_unlocked=False）。"""
    state = State.from_preset("battle")
    w_king = king_of(state, Side.WHITE)
    # 不 mark_moved
    new_w_king = w_king.at(9, 17)
    pieces = list(state.pieces)
    pieces[pieces.index(w_king)] = new_w_king
    state.pieces = pieces
    s = piece_at(state, 9, 16)  # 黑兵
    new_state, candidates = clone_offer_check(state, s)
    # 武王未移动 → side_clone_unlocked=False → 不触发
    assert candidates == []


def test_perform_clone_promotes_soldier():
    """perform_clone 将士兵变为分身。"""
    # 构造：白武王 (9, 17) + 白兵 (8, 17) → 兵是唯一候选
    state = State(
        pieces=[
            Piece(id=1, side=Side.WHITE, type=PieceType.KING, col=9, row=17, state=KingState.FREE, has_moved=True),
            Piece(id=2, side=Side.WHITE, type=PieceType.SOLDIER, col=8, row=17),
        ],
        turn=Side.WHITE,
    )
    new_state = perform_clone(state, Side.WHITE)
    promoted = piece_at(new_state, 8, 17)
    assert promoted is not None
    assert promoted.type == PieceType.CLONE
    assert promoted.is_clone is True
    assert promoted.state == KingState.FREE


def test_perform_clone_no_op_if_two_bigs():
    """场上已有 2 大 → perform_clone 不执行。"""
    state = State.from_preset("battle")
    w_king = king_of(state, Side.WHITE)
    new_w_king = w_king.at(9, 17).mark_moved()
    pieces = list(state.pieces)
    pieces[pieces.index(w_king)] = new_w_king
    state.pieces = pieces
    fake_clone = Piece(id=99, side=Side.WHITE, type=PieceType.CLONE, col=10, row=10, is_clone=True)
    state.pieces.append(fake_clone)
    s = piece_at(state, 7, 7)
    pieces = list(state.pieces)
    pieces[pieces.index(s)] = s.at(8, 8)
    state.pieces = pieces
    new_state = perform_clone(state, Side.WHITE)
    p = piece_at(new_state, 8, 8)
    assert p is not None
    assert p.type == PieceType.SOLDIER


# ===== side_unlocked / has_any_move =====


def test_side_unlocked_initial_false():
    """battle 开局：双方武王都禁锢 → side_unlocked=False。"""
    state = State.from_preset("battle")
    assert side_unlocked(state, Side.WHITE) is False
    assert side_unlocked(state, Side.BLACK) is False


def test_side_unlocked_with_clone_true():
    """有分身 → side_unlocked=True。"""
    state = State.from_preset("battle")
    fake_clone = Piece(id=99, side=Side.WHITE, type=PieceType.CLONE, col=10, row=10, is_clone=True)
    state.pieces.append(fake_clone)
    assert side_unlocked(state, Side.WHITE) is True


def test_has_any_move_initial_battle():
    """battle 开局双方都有合法移动。"""
    state = State.from_preset("battle")
    assert has_any_move(state, Side.WHITE) is True
    assert has_any_move(state, Side.BLACK) is True


# ===== check_win_loss =====


def test_win_loss_all_enemies_captured_and_unlocked():
    """对方所有大棋子（含分身）被吃 + 己方解锁 → 己方胜。"""
    state = State.from_preset("battle")
    # 移除黑武王
    pieces = [p for p in state.pieces if not (p.side == Side.BLACK and p.type == PieceType.KING)]
    state.pieces = pieces
    # 白方加一个分身 → side_unlocked(white)=True
    white_clone = Piece(id=99, side=Side.WHITE, type=PieceType.CLONE, col=10, row=10, is_clone=True)
    state.pieces.append(white_clone)
    result = check_win_loss(state)
    assert result is not None
    assert result["winner"] == Side.WHITE.value


def test_win_loss_imprisoned_no_soldiers():
    """武王禁锢 + 已方无兵 → 对方胜。"""
    state = State.from_preset("battle")
    # 移除所有白方士兵
    pieces = [p for p in state.pieces if not (p.side == Side.WHITE and p.type == PieceType.SOLDIER)]
    state.pieces = pieces
    # 白武王仍禁锢
    result = check_win_loss(state)
    assert result is not None
    assert result["winner"] == Side.BLACK.value


def test_win_loss_no_terminal_initial():
    """battle 开局未终局。"""
    state = State.from_preset("battle")
    assert check_win_loss(state) is None


# ===== position_hash =====


def test_position_hash_initial_deterministic():
    """同一局面 → 同一哈希。"""
    s1 = State.from_preset("battle")
    s2 = State.from_preset("battle")
    assert position_hash(s1) == position_hash(s2)


def test_position_hash_changes_with_turn():
    """turn 不同 → 哈希不同。"""
    s1 = State.from_preset("battle")
    s2 = State.from_preset("battle")
    s2.turn = Side.BLACK
    assert position_hash(s1) != position_hash(s2)


def test_position_hash_changes_with_piece_state():
    """武王状态变化 → 哈希不同。"""
    s1 = State.from_preset("battle")
    s2 = State.from_preset("battle")
    w_king = king_of(s1, Side.WHITE)
    pieces = list(s2.pieces)
    pieces[pieces.index(w_king)] = w_king.mark_moved()
    s2.pieces = pieces
    assert position_hash(s1) != position_hash(s2)


# ===== apply_move 完整流程 =====


def test_apply_move_simple_move():
    """简单移动：白兵 H1 → H3 (不吃子)。"""
    state = State.from_preset("battle")
    s = piece_at(state, 7, 0)  # H1
    move = Move(piece_id=s.id, from_col=7, from_row=0, to_col=7, to_row=2, capture=False)
    new_state, candidates = apply_move(state, move)
    # 位置更新
    moved = piece_at(new_state, 7, 2)
    assert moved is not None and moved.id == s.id
    # 旧位置空
    assert piece_at(new_state, 7, 0) is None
    # 不触发分身
    assert candidates == []


def test_apply_move_capture():
    """吃子：黑方死了一枚兵。"""
    state = State.from_preset("battle")
    # 构造：白兵 (5, 5) 向上？(5, 6) 有黑兵？检查：白方 F6 兵 (5, 5)，黑方 F14 兵 (5, 13)
    # 制造：白兵在 (5, 5)，向 (5, 6) 移动（不安全），改为向 (4, 5)
    # 简化：白兵 G8 (6, 7) → H7 (7, 7) (H8 是己方)... 复杂
    # 直接构造：白兵 (5, 5) 紧邻黑兵 (5, 6)
    state.pieces.append(Piece(id=99, side=Side.BLACK, type=PieceType.SOLDIER, col=5, row=6))
    s = piece_at(state, 5, 5)
    move = Move(piece_id=s.id, from_col=5, from_row=5, to_col=5, to_row=6, capture=True)
    new_state, _ = apply_move(state, move)
    # 黑兵 dead
    captured = next(p for p in new_state.pieces if p.id == 99)
    assert captured.dead is True


def test_apply_move_king_first_move_unlocks_clone():
    """武王首次移动 → 解锁分身能力。"""
    state = State.from_preset("battle")
    # 构造：黑武王在 (9, 5) 自由态
    b_king = king_of(state, Side.BLACK)
    new_b_king = b_king.at(9, 5)
    pieces = list(state.pieces)
    pieces[pieces.index(b_king)] = new_b_king
    state.pieces = pieces
    move = Move(piece_id=new_b_king.id, from_col=9, from_row=5, to_col=9, to_row=6, capture=False)
    new_state, _ = apply_move(state, move)
    assert new_state.side_clone_unlocked[Side.BLACK] is True
    final_b_king = next(p for p in new_state.pieces if p.id == b_king.id)
    assert final_b_king.has_moved is True


def test_apply_move_clone_decision_true():
    """apply_move(clone_decision=True) 立即执行分身。"""
    # 构造：白武王 (9, 17) free；白兵 (8, 17) 已在武王范围内
    state = State(
        pieces=[
            Piece(id=1, side=Side.WHITE, type=PieceType.KING, col=9, row=17, state=KingState.FREE, has_moved=True),
            Piece(id=2, side=Side.WHITE, type=PieceType.SOLDIER, col=8, row=17),
        ],
        turn=Side.WHITE,
        side_clone_unlocked={Side.WHITE: True, Side.BLACK: False},
    )
    move = Move(piece_id=2, from_col=8, from_row=17, to_col=8, to_row=17, capture=False)
    new_state, candidates = apply_move(state, move, clone_decision=True)
    # 验证：白方有分身
    has_clone = any(p.type == PieceType.CLONE for p in new_state.pieces)
    assert has_clone


def test_apply_move_does_not_mutate_input():
    """apply_move 不修改原 state。"""
    state = State.from_preset("battle")
    s = piece_at(state, 7, 0)
    move = Move(piece_id=s.id, from_col=7, from_row=0, to_col=7, to_row=2, capture=False)
    apply_move(state, move)
    # 原 state 未变
    assert piece_at(state, 7, 0) is not None
    assert piece_at(state, 7, 2) is None


# ===== end_turn =====


def test_end_turn_switches_turn():
    """end_turn 切换回合。"""
    state = State.from_preset("battle")
    new_state, term = end_turn(state)
    assert new_state.turn == Side.BLACK
    assert term is None


def test_end_turn_sets_game_over_on_win():
    """终局时设置 game_over。"""
    state = State.from_preset("battle")
    pieces = [p for p in state.pieces if not (p.side == Side.BLACK and p.type == PieceType.KING)]
    state.pieces = pieces
    # 白方加一个分身 → side_unlocked(white)=True
    white_clone = Piece(id=99, side=Side.WHITE, type=PieceType.CLONE, col=10, row=10, is_clone=True)
    state.pieces.append(white_clone)
    new_state, term = end_turn(state)
    assert new_state.game_over is not None
    assert term["winner"] == Side.WHITE.value
    # 终局不应继续切回合
    assert new_state.turn == Side.WHITE  # 保持当前方


def test_end_turn_stalemate():
    """白方王禁锢 + 无兵 → 终局（黑方胜）。"""
    state = State.from_preset("battle")
    # 移除所有白兵
    pieces = [p for p in state.pieces if not (p.side == Side.WHITE and p.type == PieceType.SOLDIER)]
    state.pieces = pieces
    # 白武王仍在 (9, 18) 禁锢（其王城内为黑方王城，但兵数足够）
    # 实际：白武王 (9, 18) 在 BLACK_PALACE (c0=7, c1=11, r0=15, r1=18) 内
    # 围困白武王的是黑方兵 H19(7,18), K17(9,16), M19(11,18) → 已被移除
    # 移除后 is_imprisoned? 没有黑兵能覆盖 → 不会禁锢
    # 强制让白武王保持 imprisoned 状态
    w_king = next(p for p in state.pieces if p.side == Side.WHITE and p.type == PieceType.KING)
    pieces = list(state.pieces)
    pieces[pieces.index(w_king)] = Piece(
        id=w_king.id,
        side=w_king.side,
        type=w_king.type,
        col=w_king.col,
        row=w_king.row,
        state=KingState.IMPRISONED_INVINCIBLE,
        is_clone=w_king.is_clone,
        has_moved=False,
        actively_unlocked=False,
        dead=False,
    )
    state.pieces = pieces
    new_state, term = end_turn(state)
    assert term is not None
    assert term["winner"] == Side.BLACK.value


def test_end_turn_threefold_repetition():
    """同一局面 3 次 → 平局。

    position_hash 包含 turn；T1 → T2 → T1 → T2 → T1 时
    T1 状态出现 3 次 → 触发平局。需要 5 次 end_turn（move 5 次）。
    """
    state = State.from_preset("battle")
    counts = {}
    # 5 次 end_turn：白→黑→白→黑→白
    for _ in range(5):
        state, term = end_turn(state, counts)
        if term is not None:
            break
    assert term is not None
    assert term["winner"] == "draw"


def test_end_turn_increments_step_count():
    """end_turn 累加 step_count。"""
    state = State.from_preset("battle")
    assert state.step_count == 0
    new_state, _ = end_turn(state)
    assert new_state.step_count == 1
