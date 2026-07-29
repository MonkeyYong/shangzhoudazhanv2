// parity_runner.js - Node.js 脚本：加载 JSON 棋谱，step through，输出 hash
//
// 用法：
//   node test/parity_runner.js <path/to/record.json>
//
// 输出格式：每行一个 positionHash（首行为初始局面，第 N+1 行为第 N 步后）
// 失败输出：stderr + 非零退出码

import * as engine from "../src/engine.js";
import fs from "node:fs";
import process from "node:process";

function run() {
  const path = process.argv[2];
  if (!path) {
    process.stderr.write("用法: node test/parity_runner.js <path/to/record.json>\n");
    process.exit(1);
  }

  let record;
  try {
    const text = fs.readFileSync(path, "utf-8");
    record = JSON.parse(text);
  } catch (e) {
    process.stderr.write(`[ERROR] 解析 JSON 失败: ${e.message}\n`);
    process.exit(1);
  }

  try {
    let state = engine.stateFromPreset(record.preset);
    const errors = engine.recordValidate(record);
    if (errors.length > 0) {
      process.stderr.write(`[INVALID] ${errors.join("; ")}\n`);
      process.exit(1);
    }

    // 初始局面 hash
    process.stdout.write(engine.positionHash(state) + "\n");

    // 逐步应用
    for (let i = 0; i < record.moves.length; i++) {
      const step = record.moves[i];
      const [fc, fr] = engine.strToCoord(step.from);
      const [tc, tr] = engine.strToCoord(step.to);
      const piece = engine.pieceAt(state, fc, fr);
      if (!piece) {
        process.stderr.write(`[ERROR] step ${i}: 无子位于 ${step.from}\n`);
        process.exit(1);
      }
      const move = {
        piece_id: piece.id,
        from_col: fc,
        from_row: fr,
        to_col: tc,
        to_row: tr,
        capture: !!step.capture,
      };
      const [newState, candidates] = engine.applyMove(state, move, !!step.clone);
      const [afterEndTurn] = engine.endTurn(newState);
      state = afterEndTurn;
      process.stdout.write(engine.positionHash(state) + "\n");
    }
  } catch (e) {
    process.stderr.write(`[ERROR] ${e.stack || e.message}\n`);
    process.exit(1);
  }
}

run();
