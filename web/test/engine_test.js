// engine_test.js - Node.js 自测，验证 engine.js 行为正确
//
// 用法：
//   cd web
//   node --experimental-vm-modules test/engine_test.js
//   或
//   node test/run.mjs

import assert from "node:assert/strict";
import * as engine from "../src/engine.js";

const tests = [];
function test(name, fn) {
  tests.push({ name, fn });
}

// ===== 基础 =====
test("stateFromPreset battle 22 子", () => {
  const s = engine.stateFromPreset("battle");
  assert.equal(s.pieces.length, 22);
  assert.equal(s.turn, "white");
});

test("stateFromPreset small 14 子", () => {
  const s = engine.stateFromPreset("small");
  assert.equal(s.pieces.length, 14);
});

test("stateFromPreset final 34 子", () => {
  const s = engine.stateFromPreset("final");
  assert.equal(s.pieces.length, 34);
});

test("stateFromPreset 未知 preset 抛错", () => {
  assert.throws(() => engine.stateFromPreset("nope"));
});

test("stateClone 独立副本", () => {
  const s = engine.stateFromPreset("battle");
  const c = engine.stateClone(s);
  assert.notEqual(c, s);
  assert.notEqual(c.pieces, s.pieces);
  assert.equal(c.pieces[0].id, s.pieces[0].id);
});

// ===== 坐标 =====
test("coordToStr / strToCoord 互转", () => {
  for (let c = 0; c < 19; c++) {
    for (let r = 0; r < 19; r++) {
      const [c2, r2] = engine.strToCoord(engine.coordToStr(c, r));
      assert.equal(c, c2);
      assert.equal(r, r2);
    }
  }
});

test("inPalace 白方", () => {
  assert.equal(engine.inPalace("white", 7, 0), true);
  assert.equal(engine.inPalace("white", 11, 3), true);
  assert.equal(engine.inPalace("white", 6, 0), false);
});

test("inPalace 黑方", () => {
  assert.equal(engine.inPalace("black", 7, 15), true);
  assert.equal(engine.inPalace("black", 11, 18), true);
  assert.equal(engine.inPalace("black", 7, 14), false);
});

// ===== 移动 =====
test("reachableCells 禁锢武王为空", () => {
  const s = engine.stateFromPreset("battle");
  const king = engine.kingOf(s, "white");
  assert.equal(king.state, "imprisoned_invincible");
  assert.deepEqual(engine.reachableCells(s, king), []);
});

test("reachableCells 兵 8 方向 × 2 格", () => {
  const s = engine.stateFromPreset("battle");
  const s_piece = engine.pieceAt(s, 5, 5); // F6 白兵
  const moves = engine.reachableCells(s, s_piece);
  assert.equal(moves.length, 14); // 16 - 2 己方阻挡
});

test("legalMoves 过滤无敌武王", () => {
  const s = engine.stateFromPreset("battle");
  const s_piece = engine.pieceAt(s, 7, 0); // H1 白兵
  const moves = engine.legalMoves(s, s_piece);
  // 不能吃 (9, 0) 的黑武王（has_moved=False）
  assert.equal(moves.some(m => m.col === 9 && m.row === 0 && m.capture), false);
});

// ===== 胜负 =====
test("checkWinLoss 初始局非终局", () => {
  const s = engine.stateFromPreset("battle");
  assert.equal(engine.checkWinLoss(s), null);
});

test("sideUnlocked 初始双方均未解锁", () => {
  const s = engine.stateFromPreset("battle");
  assert.equal(engine.sideUnlocked(s, "white"), false);
  assert.equal(engine.sideUnlocked(s, "black"), false);
});

// ===== 行动执行 =====
test("applyMove 简单移动", () => {
  const s = engine.stateFromPreset("battle");
  const p = engine.pieceAt(s, 7, 0); // H1
  const [newState] = engine.applyMove(s, {
    piece_id: p.id, from_col: 7, from_row: 0, to_col: 7, to_row: 2, capture: false,
  });
  assert.equal(engine.pieceAt(newState, 7, 2).id, p.id);
  assert.equal(engine.pieceAt(newState, 7, 0), null);
});

test("applyMove 不修改原 state", () => {
  const s = engine.stateFromPreset("battle");
  const p = engine.pieceAt(s, 7, 0);
  engine.applyMove(s, {
    piece_id: p.id, from_col: 7, from_row: 0, to_col: 7, to_row: 2, capture: false,
  });
  assert.notEqual(engine.pieceAt(s, 7, 0), null);
});

test("endTurn 切换回合", () => {
  const s = engine.stateFromPreset("battle");
  const [newState] = engine.endTurn(s);
  assert.equal(newState.turn, "black");
});

test("endTurn 累加 step_count", () => {
  const s = engine.stateFromPreset("battle");
  const [newState] = engine.endTurn(s);
  assert.equal(newState.step_count, 1);
});

// ===== Zobrist =====
test("stateHash 初始确定性", () => {
  const s1 = engine.stateFromPreset("battle");
  const s2 = engine.stateFromPreset("battle");
  assert.deepEqual(engine.stateHash(s1), engine.stateHash(s2));
});

test("stateHash turn 不同则不同", () => {
  const s1 = engine.stateFromPreset("battle");
  const s2 = engine.stateFromPreset("battle");
  s2.turn = "black";
  assert.notDeepEqual(engine.stateHash(s1), engine.stateHash(s2));
});

// ===== AI =====
test("aiChoose rookie 产出合法着法", () => {
  const s = engine.stateFromPreset("battle");
  const choice = engine.aiChoose(s, "white", engine.AI_LEVELS.rookie);
  assert.ok(choice);
  const piece = engine.pieceAt(s, choice.move.from_col, choice.move.from_row);
  assert.ok(piece);
  const legal = engine.legalMoves(s, piece);
  assert.ok(legal.some(m => m.col === choice.move.to_col && m.row === choice.move.to_row));
});

test("aiChoose advanced 产出合法着法", () => {
  const s = engine.stateFromPreset("battle");
  const choice = engine.aiChoose(s, "white", engine.AI_LEVELS.advanced);
  assert.ok(choice);
  const piece = engine.pieceAt(s, choice.move.from_col, choice.move.from_row);
  assert.ok(piece);
  const legal = engine.legalMoves(s, piece);
  assert.ok(legal.some(m => m.col === choice.move.to_col && m.row === choice.move.to_row));
});

test("aiChoose 无子可走返回 null", () => {
  const s = engine.stateFromPreset("battle");
  // 移除所有白方兵
  s.pieces = s.pieces.filter(p => !(p.side === "white" && p.type === "soldier"));
  // 强制白武王禁锢
  const wk = s.pieces.find(p => p.side === "white" && p.type === "king");
  wk.state = "imprisoned_invincible";
  const choice = engine.aiChoose(s, "white", engine.AI_LEVELS.rookie);
  assert.equal(choice, null);
});

// ===== 评估 =====
test("evaluate 简单对称局面", () => {
  const s = engine.stateFromPreset("battle");
  const wScore = engine.evaluate(s, "white");
  const bScore = engine.evaluate(s, "black");
  // 对称局面评估应接近相等
  assert.ok(Math.abs(wScore - bScore) < 200);
});

// ===== 棋谱 =====
test("recordValidate 合法 record", () => {
  const r = {
    preset: "battle",
    label: "test",
    moves: [
      { from: "H1", to: "H3", capture: false, clone: false },
      { from: "H19", to: "H17", capture: false, clone: false },
    ],
  };
  assert.deepEqual(engine.recordValidate(r), []);
});

test("recordValidate 非法 preset", () => {
  const r = { preset: "nope", label: "", moves: [] };
  const errors = engine.recordValidate(r);
  assert.ok(errors.length > 0);
});

// ===== 运行 =====
let passed = 0, failed = 0;
for (const { name, fn } of tests) {
  try {
    await fn();
    console.log(`  ✓ ${name}`);
    passed++;
  } catch (e) {
    console.error(`  ✗ ${name}`);
    console.error(`    ${e.message}`);
    failed++;
  }
}
console.log(`\n${passed}/${tests.length} passed${failed > 0 ? `, ${failed} failed` : ""}`);
process.exit(failed > 0 ? 1 : 0);
