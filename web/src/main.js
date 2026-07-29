// main.js - 入口：挂载 Game

import { Game } from "./ui.js";

window.addEventListener("DOMContentLoaded", () => {
  const canvas = document.getElementById("board");
  const panel = document.getElementById("panel");
  window.game = new Game(canvas, panel);
});
