// main.js - 入口：挂载 Game
//
// 注意：必须用 window.load（或 rAF 二次调度）而非 DOMContentLoaded
// 因为 CSS 还在加载时 canvas 的 getBoundingClientRect() 返回 0，
// 导致 fitCanvas() 把画布设成 0×0，从而棋盘表面上"看不到"。

import { Game } from "./ui.js";

function init() {
  const canvas = document.getElementById("board");
  const panel = document.getElementById("panel");
  if (!canvas || !panel) return;
  window.game = new Game(canvas, panel);
}

function startWhenReady() {
  if (document.readyState === "complete") {
    // CSS 已加载 → 直接初始化
    init();
  } else {
    // 等待 window.load（CSS 等资源完成）
    window.addEventListener("load", init, { once: true });
  }
}

startWhenReady();
