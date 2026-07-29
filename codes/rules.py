"""规则层：移动 / 吃子 / 禁锢 / 分身 / 暴走 / 胜负 / 循环检测。

权威来源：v1 codes/商周大战.html (lines 904-1260)
v2 改造：所有函数纯函数化（输入 state，输出新 state / 计算值，不修改原 state）。
"""

from __future__ import annotations

from typing import Optional

from codes.board import (
    BLACK_PALACE,
    SIZE,
    KingState,
    Move,
    Piece,
    PieceType,
    Side,
    State,
    in_palace,
)


# ===== 方向向量 =====

DIRS_8 = [
    (0, 1), (0, -1), (1, 0), (-1, 0),  # 横竖
    (1, 1), (1, -1), (-1, 1), (-1, -1),  # 斜线
]
"""8 个方向（含横竖 + 斜线）。"""

MAX_STEP_NORMAL = 2
"""普通态单步最大格数。"""

MAX_STEP_BERSERK = 18
"""暴走态射线最大格数（棋盘边长足够覆盖全棋盘）。"""


# ===== 基础查询 =====


def piece_at(state: State, col: int, row: int) -> Optional[Piece]:
    """返回 (col, row) 处的活棋子；返回 None 表示空格。"""
    for p in state.pieces:
        if p.dead:
            continue
        if p.col == col and p.row == row:
            return p
    return None


def king_of(state: State, side: Side) -> Optional[Piece]:
    """返回 side 方的本体武王（不含分身）。"""
    for p in state.pieces:
        if p.dead:
            continue
        if p.side == side and p.type == PieceType.KING and not p.is_clone:
            return p
    return None


def big_count(state: State, side: Side) -> int:
    """side 方的「大棋子」总数（武王 + 分身）。"""
    return sum(
        1
        for p in state.pieces
        if not p.dead and p.side == side and (p.type == PieceType.KING or p.type == PieceType.CLONE)
    )


def clone_count(state: State, side: Side) -> int:
    """side 方的分身数。"""
    return sum(1 for p in state.pieces if not p.dead and p.side == side and p.type == PieceType.CLONE)


def soldiers_of(state: State, side: Side) -> int:
    """side 方的活士兵数。"""
    return sum(
        1 for p in state.pieces if not p.dead and p.side == side and p.type == PieceType.SOLDIER
    )


# ===== 移动范围 =====


def _max_step(state: State, piece: Piece) -> int:
    """根据 piece 状态决定单方向最大步数。"""
    return MAX_STEP_BERSERK if piece.state == KingState.BERSERK else MAX_STEP_NORMAL


def _side_max_step(piece: Piece) -> int:
    """根据 piece 状态决定单方向最大步数（不依赖 state，性能略好）。"""
    return MAX_STEP_BERSERK if piece.state == KingState.BERSERK else MAX_STEP_NORMAL


def reachable_cells(state: State, piece: Piece) -> list[dict]:
    """理论可达格（不区分无敌武王保护）。

    路径规则：
    - 不能穿过敌方棋子（遇到敌即停，可吃）
    - 己方棋子可穿过
    - 到达外边界即停
    - 禁锢武王（imprisoned_invincible）不能动，返回空
    """
    if piece.state == KingState.IMPRISONED_INVINCIBLE:
        return []
    moves: list[dict] = []
    max_step = _side_max_step(piece)
    for dc, dr in DIRS_8:
        for s in range(1, max_step + 1):
            nc, nr = piece.col + dc * s, piece.row + dr * s
            if not (0 <= nc < SIZE and 0 <= nr < SIZE):
                break
            occ = piece_at(state, nc, nr)
            if occ is None:
                moves.append({"col": nc, "row": nr, "capture": False})
            elif occ.side != piece.side:
                moves.append({"col": nc, "row": nr, "capture": True})
                break  # 吃敌后停
            else:
                continue  # 己方可穿过，继续向同方向延伸
    return moves


def legal_moves(state: State, piece: Piece) -> list[dict]:
    """合法移动目标：reachable_cells 基础上，过滤掉无敌武王（has_moved=False 王不可被吃）。"""
    return [
        m
        for m in reachable_cells(state, piece)
        if not m["capture"]
        or not (
            (t := piece_at(state, m["col"], m["row"])) is not None
            and t.type == PieceType.KING
            and not t.has_moved
        )
    ]


def theoretical_range(state: State, king: Piece) -> set[tuple[int, int]]:
    """武王理论行动范围（2 格几何 / 暴走无限射线），忽略阻挡。

    用于：主动解锁检查、分身触发检查。
    """
    if king.type != PieceType.KING and king.type != PieceType.CLONE:
        return set()
    max_step = _side_max_step(king)
    cells: set[tuple[int, int]] = set()
    for dc, dr in DIRS_8:
        for s in range(1, max_step + 1):
            nc, nr = king.col + dc * s, king.row + dr * s
            if not (0 <= nc < SIZE and 0 <= nr < SIZE):
                break
            cells.add((nc, nr))
    return cells


# ===== 武王状态 =====


def is_imprisoned(state: State, king: Piece) -> bool:
    """武王是否被 ≥2 个敌子在 2 格吃子距离围困。

    判定依据：敌方未禁锢棋子的 reachable_cells 是否覆盖 king 位置。
    注意：敌方的无敌武王也能覆盖（虽然它不能动，但参与围困计数）。
    """
    if king.type != PieceType.KING or king.is_clone:
        return False
    n = 0
    for p in state.pieces:
        if p.dead or p.side == king.side:
            continue
        if p.state == KingState.IMPRISONED_INVINCIBLE:
            continue  # 禁锢棋子不能动，不计
        # 直接用 reachable_cells，逻辑与可达性一致
        for m in reachable_cells(state, p):
            if m["col"] == king.col and m["row"] == king.row:
                n += 1
                break
        if n >= 2:
            return True
    return False


def recompute_king_states(state: State) -> State:
    """被动重算所有「未移动且未主动解锁」的武王状态（imprisoned_invincible / free）。

    暴走态的武王不会被影响（保持 berserk）。
    """
    new_state = state.clone()
    for p in new_state.pieces:
        if p.dead or p.type != PieceType.KING or p.is_clone:
            continue
        if p.state == KingState.BERSERK:
            continue
        if p.has_moved or p.actively_unlocked:
            new_state.pieces[new_state.pieces.index(p)] = p.with_state(KingState.FREE)
        elif is_imprisoned(state, p):
            new_state.pieces[new_state.pieces.index(p)] = p.with_state(KingState.IMPRISONED_INVINCIBLE)
        else:
            new_state.pieces[new_state.pieces.index(p)] = p.with_state(KingState.FREE)
    return new_state


def active_unlock_check(state: State, moved: Piece) -> State:
    """主动解锁：刚移动的棋子若进入己方禁锢武王的理论范围，解除其禁锢。

    一旦 actively_unlocked=True，武王以后不再被动重新禁锢（仅由本方兵接应过一次）。
    """
    new_state = state.clone()
    for k in new_state.pieces:
        if k.dead or k.side != moved.side:
            continue
        if k.type != PieceType.KING or k.is_clone:
            continue
        if k.state != KingState.IMPRISONED_INVINCIBLE:
            continue
        if (moved.col, moved.row) in theoretical_range(state, k):
            idx = new_state.pieces.index(k)
            new_state.pieces[idx] = k.with_state(KingState.FREE)  # 立即置 free
            # 但 actively_unlocked 标记留在下面统一处理
            new_state.pieces[idx] = Piece(
                id=k.id,
                side=k.side,
                type=k.type,
                col=k.col,
                row=k.row,
                state=KingState.FREE,
                is_clone=k.is_clone,
                has_moved=k.has_moved,
                actively_unlocked=True,
                dead=k.dead,
            )
    return new_state


def berserk_check(state: State, moved: Piece) -> State:
    """暴走判定：武王/分身踏入己方王城 → 暴走 + 失去无敌 + 己方永久失去分身 + 对方武王解禁。

    副作用链条：
    - moved.state = berserk
    - 若 moved 是本体武王：has_moved = true
    - side_lost_clone[moved.side] = true
    - 对方所有本体武王：has_moved=true, state=free, actively_unlocked=true
    """
    new_state = state.clone()
    # 重新查找 moved（可能 piece_id 变化但 state 已更新）
    moved_updated = next((p for p in new_state.pieces if p.id == moved.id), moved)
    if moved_updated.type != PieceType.KING and moved_updated.type != PieceType.CLONE:
        return new_state
    if moved_updated.state == KingState.BERSERK:
        return new_state
    if not in_palace(moved_updated.side, moved_updated.col, moved_updated.row):
        return new_state

    # 触发暴走
    idx = new_state.pieces.index(moved_updated)
    new_berserk = Piece(
        id=moved_updated.id,
        side=moved_updated.side,
        type=moved_updated.type,
        col=moved_updated.col,
        row=moved_updated.row,
        state=KingState.BERSERK,
        is_clone=moved_updated.is_clone,
        has_moved=True if moved_updated.type == PieceType.KING else moved_updated.has_moved,
        actively_unlocked=moved_updated.actively_unlocked,
        dead=moved_updated.dead,
    )
    new_state.pieces[idx] = new_berserk
    new_state.side_lost_clone[moved_updated.side] = True

    # 对方所有本体武王解除无敌禁锢（一次性、不可逆）
    for i, k in enumerate(new_state.pieces):
        if k.dead or k.side == moved_updated.side:
            continue
        if k.type != PieceType.KING or k.is_clone:
            continue
        new_state.pieces[i] = Piece(
            id=k.id,
            side=k.side,
            type=k.type,
            col=k.col,
            row=k.row,
            state=KingState.FREE,  # 解禁锢
            is_clone=k.is_clone,
            has_moved=True,
            actively_unlocked=True,
            dead=k.dead,
        )
    return new_state


# ===== 分身 =====


def in_any_friendly_big_range(state: State, soldier: Piece) -> bool:
    """士兵是否在己方任一武王/分身的理论范围内。"""
    for k in state.pieces:
        if k.dead or k.side != soldier.side:
            continue
        if k.type != PieceType.KING and k.type != PieceType.CLONE:
            continue
        if (soldier.col, soldier.row) in theoretical_range(state, k):
            return True
    return False


def clone_offer_check(state: State, moved: Piece) -> tuple[State, list[Piece]]:
    """分身触发检测（双向）：士兵进入武王范围，或武王进入士兵范围。

    返回 (new_state, candidate_soldiers)；candidate_soldiers 是可被变身的士兵列表。
    与 v1 不同：v1 用全局 cloneOfferCells / cloneCandidates，v2 改为函数返回值（纯函数）。
    """
    new_state = state.clone()
    candidates: list[Piece] = []
    if new_state.side_lost_clone[moved.side]:
        return new_state, candidates
    if not new_state.side_clone_unlocked[moved.side]:
        return new_state, candidates
    if big_count(state, moved.side) >= 2:
        return new_state, candidates

    if moved.type == PieceType.SOLDIER:
        # 情形一：士兵进入武王移动范围
        if in_any_friendly_big_range(state, moved):
            candidates.append(moved)
    elif moved.type == PieceType.KING or moved.type == PieceType.CLONE:
        # 情形二：武王进入小棋子移动范围
        range_cells = theoretical_range(state, moved)
        for s in state.pieces:
            if s.dead or s.side != moved.side or s.type != PieceType.SOLDIER:
                continue
            if (s.col, s.row) in range_cells:
                candidates.append(s)
    return new_state, candidates


def perform_clone(state: State, side: Side) -> State:
    """执行分身：将候选士兵列表中的第一个变为武王分身（任选实现：v1 取首个）。

    副作用：
    - 士兵 → clone，state = free
    - 若分身落在己方王城，立即触发 berserk_CHECK
    - 重算武王状态
    """
    new_state = state.clone()
    candidates = [p for p in new_state.pieces if not p.dead and p.side == side and p.type == PieceType.SOLDIER]
    if not candidates:
        return new_state
    if big_count(new_state, side) >= 2:
        return new_state
    s = candidates[0]
    idx = new_state.pieces.index(s)
    new_state.pieces[idx] = Piece(
        id=s.id,
        side=s.side,
        type=PieceType.CLONE,
        col=s.col,
        row=s.row,
        state=KingState.FREE,
        is_clone=True,
        has_moved=False,
        actively_unlocked=False,
        dead=False,
    )
    # 立即判断是否踏入己方王城（按规则 5.6）
    new_state = berserk_check(new_state, new_state.pieces[idx])
    new_state = recompute_king_states(new_state)
    return new_state


# ===== 胜负 / 停棋 / 平局 =====


def side_unlocked(state: State, side: Side) -> bool:
    """某方是否处于解锁态：任一本体武王非禁锢，或存在分身。"""
    for p in state.pieces:
        if p.dead or p.side != side:
            continue
        if p.type == PieceType.CLONE:
            return True
        if p.type == PieceType.KING and p.state != KingState.IMPRISONED_INVINCIBLE:
            return True
    return False


def check_win_loss(state: State) -> Optional[dict]:
    """胜负判定（不含平局）。

    返回：
    - None：未终局
    - {"winner": "white"|"black", "reason": "..."}：已终局
    """
    w_big = big_count(state, Side.WHITE)
    b_big = big_count(state, Side.BLACK)
    # 对方所有大棋子（武王+分身）被吃光 + 己方已解锁 → 己方胜
    if w_big == 0 and side_unlocked(state, Side.BLACK):
        return {"winner": Side.BLACK.value, "reason": "black_kings_all_captured"}
    if b_big == 0 and side_unlocked(state, Side.WHITE):
        return {"winner": Side.WHITE.value, "reason": "white_kings_all_captured"}
    # 王被禁锢 + 己方无兵 → 对方胜（不能行动即死）
    w_king = king_of(state, Side.WHITE)
    b_king = king_of(state, Side.BLACK)
    if w_king and w_king.state == KingState.IMPRISONED_INVINCIBLE and soldiers_of(state, Side.WHITE) == 0:
        return {"winner": Side.BLACK.value, "reason": "white_king_imprisoned_no_soldiers"}
    if b_king and b_king.state == KingState.IMPRISONED_INVINCIBLE and soldiers_of(state, Side.BLACK) == 0:
        return {"winner": Side.WHITE.value, "reason": "black_king_imprisoned_no_soldiers"}
    return None


def has_any_move(state: State, side: Side) -> bool:
    """某方是否有任何合法移动（停棋判定）。"""
    for p in state.pieces:
        if p.dead or p.side != side:
            continue
        if legal_moves(state, p):
            return True
    return False


# ===== 局面哈希 =====


def position_hash(state: State) -> str:
    """局面哈希（用于循环局面检测 + Parity 测试）。

    包含：每枚活棋子的 side/type/pos/state/has_moved/actively_unlocked + turn + 标志位。
    """
    arr = sorted(
        f"{p.side.value[0]}{p.type.value[0]}{p.col},{p.row},{p.state.value[0]}"
        f"{1 if p.has_moved else 0}{1 if p.actively_unlocked else 0}"
        for p in state.pieces
        if not p.dead
    )
    return (
        state.turn.value
        + "|"
        + "|".join(arr)
        + "|"
        + f"{1 if state.side_lost_clone[Side.WHITE] else 0}"
        f"{1 if state.side_lost_clone[Side.BLACK] else 0}"
        f"{1 if state.side_clone_unlocked[Side.WHITE] else 0}"
        f"{1 if state.side_clone_unlocked[Side.BLACK] else 0}"
    )


# ===== 行动执行 =====


def _apply_move_inplace(state: State, move: Move) -> State:
    """应用 move 到 state（内部使用，直接 mutate state.pieces）。

    副作用：
    - 吃子：target 标记 dead
    - 移动：piece 位置更新
    - 武王首次移动：has_moved=true, side_clone_unlocked[side]=true
    - 暴走判定（若踏入己方王城）
    - 主动解锁（若接应己方武王）
    - 分身触发（仅检查，不执行）
    - 被动重算武王状态
    """
    # 1. 吃子
    piece = next(p for p in state.pieces if p.id == move.piece_id)
    if move.capture:
        target = piece_at(state, move.to_col, move.to_row)
        if target is not None and target.side != piece.side:
            idx = state.pieces.index(target)
            state.pieces[idx] = target.mark_dead()
            # 暂时不删，保持索引稳定（与 v1 行为一致：标记 dead）

    # 2. 移动
    idx = state.pieces.index(piece)
    moved = piece.at(move.to_col, move.to_row)
    state.pieces[idx] = moved

    # 3. 武王首次移动：失去无敌 + 解锁分身能力
    if moved.type == PieceType.KING and not moved.is_clone and not moved.has_moved:
        state.pieces[idx] = moved.mark_moved()
        state.side_clone_unlocked[moved.side] = True
        moved = state.pieces[idx]

    # 4. 暴走判定
    state = berserk_check(state, moved)

    # 5. 主动解锁
    state = active_unlock_check(state, moved)

    # 6. 被动重算
    state = recompute_king_states(state)
    return state


def apply_move(state: State, move: Move, clone_decision: bool = False) -> tuple[State, list[Piece]]:
    """应用 move 到 state，返回 (new_state, clone_candidates)。

    - 若 clone 触发，返回候选士兵；调用方可决定是否执行 perform_clone
    - 若 clone_decision=True，立即执行分身（候选士兵列表非空时）
    - 否则仅返回候选，不执行
    """
    new_state = state.clone()
    move_piece = next((p for p in new_state.pieces if p.id == move.piece_id), None)
    if move_piece is None:
        raise ValueError(f"找不到 piece_id={move.piece_id}")

    # 1. 吃子
    if move.capture:
        target = piece_at(new_state, move.to_col, move.to_row)
        if target is not None and target.side != move_piece.side:
            idx = new_state.pieces.index(target)
            new_state.pieces[idx] = target.mark_dead()

    # 2. 移动
    idx = new_state.pieces.index(move_piece)
    moved = move_piece.at(move.to_col, move.to_row)
    new_state.pieces[idx] = moved

    # 3. 武王首次移动 → 解锁分身能力
    if moved.type == PieceType.KING and not moved.is_clone and not moved.has_moved:
        new_state.pieces[idx] = moved.mark_moved()
        new_state.side_clone_unlocked[moved.side] = True
        moved = new_state.pieces[idx]

    # 4. 暴走判定
    new_state = berserk_check(new_state, moved)

    # 5. 主动解锁
    new_state = active_unlock_check(new_state, moved)

    # 6. 分身检测
    new_state, candidates = clone_offer_check(new_state, moved)

    # 7. 被动重算
    new_state = recompute_king_states(new_state)

    # 8. 若决策是接受分身，立即执行
    if clone_decision and candidates:
        new_state = perform_clone(new_state, moved.side)
        candidates = []  # 已执行，候选清空

    return new_state, candidates


def end_turn(state: State, position_count: Optional[dict] = None) -> tuple[State, Optional[dict]]:
    """切换回合 + 终局判定 + 平局检测。

    返回 (new_state, terminal)：
    - terminal: None | {"winner": ..., "reason": ...} | {"winner": "draw", "reason": "threefold_repetition"}
    - 若传入 position_count（dict），用于循环局面累计；返回 new_state 含 game_over + 累计后的 dict
    """
    new_state = state.clone()
    new_state.step_count += 1

    # 1. 胜负判定
    term = check_win_loss(new_state)
    if term:
        new_state.game_over = term
        return new_state, term

    # 2. 切换回合
    new_state.turn = new_state.turn.opposite

    # 3. 停棋负
    if not has_any_move(new_state, new_state.turn):
        winner = new_state.turn.opposite
        term = {"winner": winner.value, "reason": "stalemate"}
        new_state.game_over = term
        return new_state, term

    # 4. 平局：同一局面出现 3 次
    if position_count is not None:
        h = position_hash(new_state)
        position_count[h] = position_count.get(h, 0) + 1
        if position_count[h] >= 3:
            term = {"winner": "draw", "reason": "threefold_repetition"}
            new_state.game_over = term
            return new_state, term

    return new_state, None
