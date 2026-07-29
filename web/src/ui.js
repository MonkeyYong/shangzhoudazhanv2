// ui.js - 交互层 + 游戏循环
//
// 状态：
//   state        - 当前 State
//   record       - 棋谱 Record
//   selected     - 选中的棋子（Piece 或 null）
//   legalMoves   - 选中棋子的合法着法
//   mode         - "play" | "replay"
//   replayIndex  - 复盘模式下当前回放步数
//   aiTimer      - AI 异步思考定时器

import {
  SIDE, PIECE_TYPE, KING_STATE,
  stateFromPreset, stateClone,
  pieceAt, legalMoves, applyMove, endTurn,
  positionHash, AI_LEVELS, aiChoose,
  recordFromDict, recordToDict, recordValidate,
  coordToStr, strToCoord,
} from "./engine.js";

import { render, fitCanvas, fitCanvasWhenReady, canvasToCell } from "./render.js";

export class Game {
  constructor(canvas, panel) {
    this.canvas = canvas;
    this.panel = panel;
    this.ctx = canvas.getContext("2d");
    this.state = stateFromPreset("battle");
    this.record = { preset: "battle", label: "", moves: [] };
    this.selected = null;
    this.legalMoves = [];
    this.mode = "play"; // "play" | "replay"
    this.replayIndex = 0;
    this.opponent = "human"; // "human" | "ai-white" | "ai-black"
    this.aiLevel = "advanced";
    this.aiTimer = null;
    this.lastMove = null;

    this._setupListeners();
    this._setupPanel();
    this._scheduleRender();
  }

  // ===== 初始化 =====

  _setupListeners() {
    this.canvas.addEventListener("click", (e) => this._onClick(e));
    this.canvas.addEventListener("mousemove", (e) => this._onHover(e));
    this.canvas.addEventListener("mouseleave", () => {
      this._hoverCell = null;
      this._scheduleRender();
    });
    window.addEventListener("resize", () => {
      fitCanvas(this.canvas);
      this._scheduleRender();
    });
  }

  _setupPanel() {
    this.panel.querySelector("#btn-new").addEventListener("click", () => this.newGame());
    this.panel.querySelector("#btn-undo").addEventListener("click", () => this.undo());
    this.panel.querySelector("#btn-export").addEventListener("click", () => this.exportRecord());
    this.panel.querySelector("#btn-import").addEventListener("click", () => {
      this.panel.querySelector("#file-import").click();
    });
    this.panel.querySelector("#file-import").addEventListener("change", (e) => this.importRecord(e));

    this.panel.querySelector("#preset").addEventListener("change", (e) => {
      this.newGame(e.target.value);
    });
    this.panel.querySelector("#opponent").addEventListener("change", (e) => {
      this.opponent = e.target.value;
      this.panel.querySelector("#level").disabled = this.opponent === "human";
      this._scheduleRender();
      this._maybeScheduleAI();
    });
    this.panel.querySelector("#level").addEventListener("change", (e) => {
      this.aiLevel = e.target.value;
    });

    // 多次重试 fitCanvas（防御 CSS 异步加载 / 布局延迟）
    fitCanvasWhenReady(this.canvas);
  }

  // ===== 事件 =====

  _onClick(e) {
    if (this.mode !== "play") return;
    if (this._isAIThinking()) return;
    if (this.state.game_over) return;

    const cell = canvasToCell(this.canvas, e);
    if (!cell) return;
    const [col, row] = cell;

    const piece = pieceAt(this.state, col, row);

    if (this.selected) {
      // 已有选中：尝试落子
      const move = this.legalMoves.find(m => m.col === col && m.row === row);
      if (move) {
        this._applyMove(this.selected, move);
        return;
      }
      // 点击的是己方其他棋子 → 切换选中
      if (piece && piece.side === this.state.turn) {
        this._select(piece);
        return;
      }
      // 点击空白/敌方 → 取消选中
      this._deselect();
      return;
    }

    // 无选中：点击己方棋子 → 选中
    if (piece && piece.side === this.state.turn) {
      this._select(piece);
    }
  }

  _onHover(e) {
    const cell = canvasToCell(this.canvas, e);
    if (!cell) {
      if (this._hoverCell !== null) {
        this._hoverCell = null;
        this._scheduleRender();
      }
      return;
    }
    const [col, row] = cell;
    if (this._hoverCell && this._hoverCell.col === col && this._hoverCell.row === row) return;
    this._hoverCell = { col, row };
    this._scheduleRender();
  }

  // ===== 选中 / 落子 =====

  _select(piece) {
    this.selected = piece;
    this.legalMoves = legalMoves(this.state, piece);
    this._scheduleRender();
  }

  _deselect() {
    this.selected = null;
    this.legalMoves = [];
    this._scheduleRender();
  }

  _applyMove(piece, move) {
    const moveRecord = {
      from_col: piece.col,
      from_row: piece.row,
      to_col: move.col,
      to_row: move.row,
      capture: move.capture,
      clone: false,
    };

    const [newState, candidates] = applyMove(
      this.state,
      { ...moveRecord, piece_id: piece.id },
      false,
    );

    // 分身确认（v1 有弹窗；v2 简化：自动接受）
    let finalState = newState;
    if (candidates.length > 0) {
      moveRecord.clone = true;
      const [c] = applyMove(this.state, { ...moveRecord, piece_id: piece.id }, true);
      finalState = c;
    }

    const [s1, term] = endTurn(finalState);
    this.state = s1;
    this.record.moves.push(moveRecord);
    this.lastMove = moveRecord;
    this._selected = null;
    this.selected = null;
    this.legalMoves = [];

    this._scheduleRender();
    this._renderScoresheet();

    if (term) {
      this._announce(term);
    } else {
      this._maybeScheduleAI();
    }
  }

  undo() {
    if (this.mode !== "play") return;
    if (this._isAIThinking()) return;
    if (this.record.moves.length === 0) return;
    // 撤销最后一步（简化：重建整个状态）
    this.record.moves.pop();
    this.state = stateFromPreset(this.record.preset);
    for (const m of this.record.moves) {
      const [fc, fr] = [m.from_col, m.from_row];
      const [tc, tr] = [m.to_col, m.to_row];
      const piece = pieceAt(this.state, fc, fr);
      if (!piece) break;
      const [newState] = applyMove(
        this.state,
        { ...m, from_col: fc, from_row: fr, to_col: tc, to_row: tr, piece_id: piece.id },
        !!m.clone,
      );
      const [s1] = endTurn(newState);
      this.state = s1;
    }
    this.lastMove = this.record.moves[this.record.moves.length - 1] || null;
    this._deselect();
    this._scheduleRender();
    this._renderScoresheet();
  }

  // ===== 新局 / 棋谱 =====

  newGame(preset) {
    if (preset) this.record.preset = preset;
    this.state = stateFromPreset(this.record.preset);
    this.record.moves = [];
    this.selected = null;
    this.legalMoves = [];
    this.lastMove = null;
    this._scheduleRender();
    this._renderScoresheet();
    this._setHint("点击棋子选中，再点目标格落子。");
    this._maybeScheduleAI();
  }

  exportRecord() {
    const data = recordToDict(this.record);
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `shangzhoudazhan-${this.record.preset}-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
    this._setHint("棋谱已导出。");
  }

  importRecord(e) {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      try {
        const data = JSON.parse(ev.target.result);
        const errors = recordValidate(data);
        if (errors.length > 0) {
          this._setHint(`棋谱无效: ${errors[0]}`);
          return;
        }
        this.record = recordFromDict(data);
        // 重放至当前局面
        this.state = stateFromPreset(this.record.preset);
        for (let i = 0; i < this.record.moves.length; i++) {
          const m = this.record.moves[i];
          const piece = pieceAt(this.state, m.from_col, m.from_row);
          if (!piece) break;
          const [newState] = applyMove(
            this.state,
            { ...m, piece_id: piece.id, capture: !!m.capture },
            !!m.clone,
          );
          const [s1] = endTurn(newState);
          this.state = s1;
        }
        this._renderScoresheet();
        this._scheduleRender();
        this._setHint(`已导入 ${this.record.moves.length} 步棋谱。`);
      } catch (e) {
        this._setHint(`导入失败: ${e.message}`);
      }
    };
    reader.readAsText(file);
    e.target.value = "";
  }

  // ===== AI =====

  _isAIThinking() {
    return this.aiTimer !== null;
  }

  _maybeScheduleAI() {
    if (this.state.game_over) return;
    if (this.opponent === "human") return;
    if (this.state.turn === SIDE.WHITE && this.opponent !== "ai-white") return;
    if (this.state.turn === SIDE.BLACK && this.opponent !== "ai-black") return;

    this._setHint("AI 思考中...");
    this.aiTimer = setTimeout(() => {
      this.aiTimer = null;
      this._doAIMove();
    }, 50);
  }

  _doAIMove() {
    if (this.state.game_over) return;
    const level = AI_LEVELS[this.aiLevel];
    const choice = aiChoose(this.state, this.state.turn, level);
    if (!choice) {
      this._setHint("AI 无子可走。");
      return;
    }
    const piece = pieceAt(this.state, choice.move.from_col, choice.move.from_row);
    if (!piece) return;

    const moveRecord = {
      from_col: choice.move.from_col,
      from_row: choice.move.from_row,
      to_col: choice.move.to_col,
      to_row: choice.move.to_row,
      capture: choice.move.capture,
      clone: choice.clone,
    };

    const [newState] = applyMove(
      this.state,
      { ...moveRecord, piece_id: piece.id },
      !!choice.clone,
    );
    const [s1, term] = endTurn(newState);
    this.state = s1;
    this.record.moves.push(moveRecord);
    this.lastMove = moveRecord;

    this._setHint(
      `AI: ${coordToStr(choice.move.from_col, choice.move.from_row)}→${coordToStr(choice.move.to_col, choice.move.to_row)}` +
      (choice.move.capture ? "x" : "") +
      (choice.clone ? "★" : "") +
      ` (${choice.time_ms}ms, ${choice.nodes} nodes)`,
    );
    this._renderScoresheet();
    this._scheduleRender();

    if (term) {
      this._announce(term);
    } else {
      this._maybeScheduleAI();
    }
  }

  // ===== 渲染 =====

  _scheduleRender() {
    if (this._renderQueued) return;
    this._renderQueued = true;
    requestAnimationFrame(() => {
      this._renderQueued = false;
      this._render();
    });
  }

  _render() {
    try {
      render(this.ctx, this.state, {
        selected: this.selected,
        legalMoves: this.legalMoves,
        hoverCell: this._hoverCell,
        lastMove: this.lastMove,
      });
    } catch (e) {
      console.error("[Game._render] render failed:", e, e.stack);
    }
    this._renderPanel();
  }

  _renderPanel() {
    const turnEl = this.panel.querySelector("#turn");
    const banner = this.panel.querySelector("#turn-banner");
    if (this.state.turn === SIDE.WHITE) {
      turnEl.textContent = "白方 · 周";
      banner.className = "turn-banner white";
    } else {
      turnEl.textContent = "黑方 · 商";
      banner.className = "turn-banner black";
    }

    const wKing = this.state.pieces.find(p => p.side === "white" && p.type === "king" && !p.is_clone);
    const bKing = this.state.pieces.find(p => p.side === "black" && p.type === "king" && !p.is_clone);
    updateKingCard(this.panel.querySelector("#w-king-state"), wKing);
    updateKingCard(this.panel.querySelector("#b-king-state"), bKing);
    this.panel.querySelector("#w-clone-count").textContent = this.state.pieces.filter(p => p.side === "white" && p.type === "clone").length;
    this.panel.querySelector("#b-clone-count").textContent = this.state.pieces.filter(p => p.side === "black" && p.type === "clone").length;
    this.panel.querySelector("#step-count").textContent = this.record.moves.length;
  }

  _renderScoresheet() {
    const sheet = this.panel.querySelector("#scoresheet");
    if (this.record.moves.length === 0) {
      sheet.innerHTML = '<div style="color:#888">尚无棋谱。</div>';
      return;
    }
    const html = this.record.moves.map((m, i) => {
      const num = i + 1;
      const notation = `${coordToStr(m.from_col, m.from_row)}→${coordToStr(m.to_col, m.to_row)}${m.capture ? "x" : ""}${m.clone ? "★" : ""}`;
      const cls = ["ss-move"];
      if (m.capture) cls.push("ss-capture");
      if (m.clone) cls.push("ss-clone");
      return `<span class="${cls.join(" ")}" data-i="${i}">${num}.${notation}</span>`;
    }).join("");
    sheet.innerHTML = html;
  }

  _setHint(text) {
    this.panel.querySelector("#hint").textContent = text;
  }

  _announce(term) {
    if (term.winner === "draw") {
      this._setHint("平局！局面循环 3 次。");
    } else if (term.reason === "stalemate") {
      const w = term.winner === "white" ? "白" : "黑";
      this._setHint(`${w}方胜（对方无棋可走）！`);
    } else {
      const w = term.winner === "white" ? "白" : "黑";
      this._setHint(`${w}方胜！`);
    }
  }
}

function updateKingCard(el, king) {
  if (!king) {
    el.textContent = "已死";
    el.className = "kc-state st-dead";
    return;
  }
  if (king.state === KING_STATE.BERSERK) {
    el.textContent = "暴走";
    el.className = "kc-state st-berserk";
  } else if (king.state === KING_STATE.FREE) {
    el.textContent = "自由";
    el.className = "kc-state st-free";
  } else {
    el.textContent = "武王禁锢";
    el.className = "kc-state st-imprisoned";
  }
}
