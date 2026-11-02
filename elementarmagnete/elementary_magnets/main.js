"use strict";

/**
 * Elementary magnets: two-dimensional, dimensionless planar spin model.
 *
 * Physics and parameters follow the original Python/PyScript implementation:
 *  - nearest-neighbor exchange, spatially varying easy-axis anisotropy,
 *    long-range dipole interactions, and a movable external dipole source;
 *  - overdamped angular relaxation with Euler-Maruyama thermal noise;
 *  - initial zero-temperature relaxation for ferromagnetic samples.
 *
 * No Python runtime, NumPy, build tools, or third-party JavaScript libraries.
 * Color convention: north pole = red, south pole = blue.
 */

const COLS = 24;
const ROWS = 16;
const N = COLS * ROWS;
const DEFAULT_SEED = 7319;
const MODEL_DT = 0.012;
const MODEL_TIME_PER_SECOND = 1.8;
const MAX_STEPS_PER_FRAME = 12;
const DEFAULT_T = 0.08;
const DIPOLAR_STRENGTH = 0.32;

const PRESETS = Object.freeze({
  soft: { material: "ferro", j: 0.85, anisotropy: 0.05, pinning: 0.10 },
  hard: { material: "ferro", j: 0.85, anisotropy: 0.15, pinning: 0.70 },
  para: { material: "para", j: 0, anisotropy: 0, pinning: 0 },
});

const W = 1120;
const H = 560;
const CELL = 22;
const PROBE_X = 500;
const PROBE_Y = 104;
const PROBE_W = COLS * CELL;
const PROBE_H = ROWS * CELL;
const PROBE_CX = PROBE_X + PROBE_W / 2;
const PROBE_CY = PROBE_Y + PROBE_H / 2;

const MAGNET_W = 156;
const MAGNET_H = 52;
const MAGNET_MOMENT = 750;
const SOURCE_CORE = 1.15;
const PARK_X = 175;
const PARK_Y = PROBE_CY;

const INK = "#1e293b";
const NORTH = "#ca4c49"; // North = red
const SOUTH = "#356ab5"; // South = blue
const FIELD_COLOR = "#708795";
const TAU = 2 * Math.PI;

function clamp(x, lo, hi) { return Math.max(lo, Math.min(hi, x)); }
function wrapAngle(theta) { return ((theta + Math.PI) % TAU + TAU) % TAU - Math.PI; }

// Reproducible random stream for each reset. The sequence differs from NumPy's
// PCG64, but the uniform and Gaussian distributions are the same.
class SeededRandom {
  constructor(seed) { this.seed = seed >>> 0 || 1; this.spare = null; }
  uniform() {
    let x = this.seed;
    x ^= x << 13;
    x ^= x >>> 17;
    x ^= x << 5;
    this.seed = x >>> 0;
    return this.seed / 4294967296;
  }
  normal() {
    if (this.spare !== null) {
      const z = this.spare;
      this.spare = null;
      return z;
    }
    const u1 = Math.max(Number.MIN_VALUE, this.uniform());
    const u2 = this.uniform();
    const radius = Math.sqrt(-2 * Math.log(u1));
    const angle = TAU * u2;
    this.spare = radius * Math.sin(angle);
    return radius * Math.cos(angle);
  }
}

/**
 * Pairwise 3D dipolar interaction tensor evaluated on a 2D lattice, using
 * precisely the same in-plane components as the Python model.
 */
class MagneticModel {
  constructor(cols = COLS, rows = ROWS, seed = DEFAULT_SEED) {
    this.cols = cols;
    this.rows = rows;
    this.n = cols * rows;
    this.seed = seed;
    this.positionsX = new Float64Array(this.n);
    this.positionsY = new Float64Array(this.n);
    this.neighbors = new Array(this.n);
    for (let row = 0; row < rows; row++) {
      for (let col = 0; col < cols; col++) {
        const i = row * cols + col;
        this.positionsX[i] = col - (cols - 1) / 2;
        this.positionsY[i] = row - (rows - 1) / 2;
        const neighbors = [];
        if (col > 0) neighbors.push(i - 1);
        if (col + 1 < cols) neighbors.push(i + 1);
        if (row > 0) neighbors.push(i - cols);
        if (row + 1 < rows) neighbors.push(i + cols);
        this.neighbors[i] = neighbors;
      }
    }

    // Row-major: [target * N + source]. Self-field is excluded.
    const nn = this.n * this.n;
    this.dxx = new Float64Array(nn);
    this.dxy = new Float64Array(nn);
    this.dyy = new Float64Array(nn);
    for (let i = 0; i < this.n; i++) {
      const offset = i * this.n;
      for (let j = 0; j < this.n; j++) {
        if (i === j) continue;
        const dx = this.positionsX[i] - this.positionsX[j];
        const dy = this.positionsY[i] - this.positionsY[j];
        const r2 = dx * dx + dy * dy;
        const inv3 = Math.pow(r2, -1.5);
        const inv5 = Math.pow(r2, -2.5);
        this.dxx[offset + j] = 3 * dx * dx * inv5 - inv3;
        this.dxy[offset + j] = 3 * dx * dy * inv5;
        this.dyy[offset + j] = 3 * dy * dy * inv5 - inv3;
      }
    }

    this.theta = new Float64Array(this.n);
    this.sx = new Float64Array(this.n);
    this.sy = new Float64Array(this.n);
    this.torque = new Float64Array(this.n);
    this.k = new Float64Array(this.n);
    this.random = new SeededRandom(seed);
    this.temperature = DEFAULT_T;
    this.elapsed = 0;
    this.applyPreset("soft");
    this.initialize("domains");
  }

  applyPreset(name) {
    const preset = PRESETS[name];
    if (!preset) throw new Error(`Unknown material preset: ${name}`);
    this.preset = name;
    this.material = preset.material;
    this.j = preset.j;
    this.anisotropy = preset.anisotropy;
    this.pinning = preset.pinning;
    const defects = [
      [0, 0], [-0.28, 0], [0.28, 0],
      [-0.18, 0.28], [0.18, -0.28], [0.18, 0.28], [-0.18, -0.28],
    ];
    for (let i = 0; i < this.n; i++) {
      const x = this.positionsX[i] / this.cols;
      const y = this.positionsY[i] / this.rows;
      let profile = 1;
      for (const [cx, cy] of defects) {
        const q = (x - cx) ** 2 / 0.011 + (y - cy) ** 2 / 0.009;
        profile -= this.pinning * Math.exp(-q);
      }
      this.k[i] = this.anisotropy * Math.max(profile, 0.10);
    }
  }

  initialize(initial = "domains") {
    this.elapsed = 0;
    this.random = new SeededRandom(this.seed);
    for (let i = 0; i < this.n; i++) {
      let angle;
      if (this.material === "para") angle = -Math.PI + TAU * this.random.uniform();
      else if (initial === "magnetized") angle = 0;
      else angle = Math.atan2(this.positionsY[i], this.positionsX[i]) + Math.PI / 2;
      this.theta[i] = wrapAngle(angle);
    }
    this.updateSpins();
  }

  updateSpins() {
    for (let i = 0; i < this.n; i++) {
      this.sx[i] = Math.cos(this.theta[i]);
      this.sy[i] = Math.sin(this.theta[i]);
    }
  }

  /** Computes torque s_x H_y - s_y H_x for all spins. */
  calculateTorque(external) {
    this.updateSpins();
    const ferro = this.material === "ferro";
    for (let i = 0; i < this.n; i++) {
      let fx = external[2 * i];
      let fy = external[2 * i + 1];
      if (ferro) {
        for (const j of this.neighbors[i]) {
          fx += this.j * this.sx[j];
          fy += this.j * this.sy[j];
        }
        fx += 2 * this.k[i] * this.sx[i];
        const start = i * this.n;
        let bx = 0;
        let by = 0;
        for (let j = 0; j < this.n; j++) {
          const ij = start + j;
          bx += this.dxx[ij] * this.sx[j] + this.dxy[ij] * this.sy[j];
          by += this.dxy[ij] * this.sx[j] + this.dyy[ij] * this.sy[j];
        }
        fx += DIPOLAR_STRENGTH * bx;
        fy += DIPOLAR_STRENGTH * by;
      }
      this.torque[i] = this.sx[i] * fy - this.sy[i] * fx;
    }
    return this.torque;
  }

  /** Euler-Maruyama with the same field-dependent substep criterion as Python. */
  step(external, dt = MODEL_DT, temperature = this.temperature) {
    if (!(dt > 0) || temperature < 0) throw new Error("Invalid time step or temperature");
    let maxExternal = 0;
    for (let i = 0; i < this.n; i++) {
      const magnitude = Math.hypot(external[2 * i], external[2 * i + 1]);
      if (magnitude > maxExternal) maxExternal = magnitude;
    }
    const stiffness = maxExternal + 8 * this.j + 4 * this.anisotropy + 8;
    const parts = Math.max(1, Math.ceil(dt * stiffness / 0.3));
    const h = dt / parts;
    const noise = temperature > 0 ? Math.sqrt(2 * temperature * h) : 0;
    for (let sub = 0; sub < parts; sub++) {
      this.calculateTorque(external);
      for (let i = 0; i < this.n; i++) {
        this.theta[i] = wrapAngle(this.theta[i] + h * this.torque[i] + (noise ? noise * this.random.normal() : 0));
      }
    }
    this.elapsed += dt;
    this.updateSpins();
  }

  observables() {
    this.updateSpins();
    let mx = 0, my = 0;
    for (let i = 0; i < this.n; i++) { mx += this.sx[i]; my += this.sy[i]; }
    mx /= this.n;
    my /= this.n;
    return [mx, my, Math.hypot(mx, my)];
  }
}

// External magnet: seven parallel soft-core dipoles; coordinates in model units.
function canvasToWorld(x, y) {
  return [(x - PROBE_CX) / CELL, (PROBE_CY - y) / CELL];
}
function sourceField(posX, posY, magnetX, magnetY, polarity = 1, enabled = true) {
  const length = posX.length;
  const field = new Float64Array(length * 2);
  if (!enabled) return field;
  const sourceY = (PROBE_CY - magnetY) / CELL;
  const strength = polarity * MAGNET_MOMENT / 7;
  for (let s = 0; s < 7; s++) {
    const offset = MAGNET_W * 0.37 * (-1 + 2 * s / 6);
    const sourceX = (magnetX + offset - PROBE_CX) / CELL;
    for (let i = 0; i < length; i++) {
      const dx = posX[i] - sourceX;
      const dy = posY[i] - sourceY;
      const r2 = dx * dx + dy * dy + SOURCE_CORE * SOURCE_CORE;
      const inv3 = Math.pow(r2, -1.5);
      const inv5 = Math.pow(r2, -2.5);
      field[2 * i] += (3 * dx * dx * inv5 - inv3) * strength;
      field[2 * i + 1] += 3 * dx * dy * inv5 * strength;
    }
  }
  return field;
}
function constrainMagnet(x, y) {
  return [
    clamp(x, MAGNET_W / 2 + 18, W - MAGNET_W / 2 - 18),
    clamp(y, MAGNET_H / 2 + 18, H - MAGNET_H / 2 - 18),
  ];
}

class MagnetApplet {
  constructor() {
    const ids = [
      "simulation-canvas", "experiment-controls", "material", "initial-state",
      "temperature", "temperature-value", "show-field", "toggle-magnet", "flip-poles",
      "start-pause", "reset", "run-dot", "run-label", "material-badge",
      "loading-panel", "loading-title", "loading-details",
    ];
    this.nodes = Object.fromEntries(ids.map(id => [id, document.getElementById(id)]));
    const missing = ids.filter(id => !this.nodes[id]);
    if (missing.length) throw new Error(`Missing HTML elements: ${missing.join(", ")}`);

    this.canvas = this.nodes["simulation-canvas"];
    this.ctx = this.canvas.getContext("2d");
    if (!this.ctx) throw new Error("This browser does not support 2D Canvas");
    this.model = new MagneticModel();
    this.busy = true;
    this.failed = false;
    this.running = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    this.magnetX = PARK_X;
    this.magnetY = PARK_Y;
    this.magnetEnabled = false;
    this.polarity = 1;
    this.dragPointer = null;
    this.dragOffset = [0, 0];
    this.showField = true;
    this.fieldDirty = true;
    this.external = new Float64Array(this.model.n * 2);
    this.lastTimestamp = null;
    this.accumulator = 0;
    this.lastDraw = -1000;
    this.lastFieldDraw = -1000;
    this.cachedField = [];
    this.pixelRatio = 0;
    this.displayValues = {};
    this.palette = Array.from({length: 24}, (_, i) => `hsla(${i * 15}, 42%, 67%, 0.22)`);
    this.centers = Array.from({length: this.model.n}, (_, i) => [
      PROBE_CX + CELL * this.model.positionsX[i],
      PROBE_CY - CELL * this.model.positionsY[i],
    ]);
    this.fieldPixels = [];
    const fieldX = [];
    const fieldY = [];
    for (let y = 62; y < H - 24; y += 42) {
      for (let x = 28; x < W - 18; x += 42) {
        this.fieldPixels.push([x, y]);
        const [wx, wy] = canvasToWorld(x, y);
        fieldX.push(wx);
        fieldY.push(wy);
      }
    }
    this.fieldWorldX = Float64Array.from(fieldX);
    this.fieldWorldY = Float64Array.from(fieldY);
    this.animationFrame = this.animationFrame.bind(this);
    this.installEvents();
  }

  text(id, value) {
    const str = String(value);
    if (this.displayValues[id] !== str) {
      this.nodes[id].textContent = str;
      this.displayValues[id] = str;
    }
  }
  decimal(value, digits = 2) {
    const rounded = Math.abs(value) < 0.5 * 10 ** (-digits) ? 0 : value;
    return rounded.toFixed(digits);
  }
  installEvents() {
    const listen = (id, event, handler) => this.nodes[id].addEventListener(event, handler);
    listen("material", "change", () => this.requestReset());
    listen("initial-state", "change", () => this.requestReset());
    listen("reset", "click", () => this.requestReset());
    listen("start-pause", "click", () => this.toggleRunning());
    listen("toggle-magnet", "click", () => this.toggleMagnet());
    listen("flip-poles", "click", () => this.flipPoles());
    listen("temperature", "input", () => this.onTemperature());
    listen("show-field", "change", () => this.onDisplay());
    listen("simulation-canvas", "pointerdown", event => this.onPointerDown(event));
    listen("simulation-canvas", "pointermove", event => this.onPointerMove(event));
    listen("simulation-canvas", "pointerup", event => this.onPointerEnd(event));
    listen("simulation-canvas", "pointercancel", event => this.onPointerEnd(event));
    listen("simulation-canvas", "lostpointercapture", event => this.onPointerEnd(event));
    document.addEventListener("visibilitychange", () => this.onVisibility());
  }
  async start() {
    await this.resetExperiment();
    if (!this.failed) window.requestAnimationFrame(this.animationFrame);
  }
  async resetExperiment() {
    if (this.failed) return;
    this.busy = true;
    this.nodes["experiment-controls"].disabled = true;
    this.nodes["loading-panel"].hidden = false;
    this.nodes["loading-panel"].classList.remove("load-error");
    this.text("loading-title", "Preparing the initial state…");
    this.text("loading-details", "");
    try {
      this.model.applyPreset(this.nodes.material.value);
      this.model.temperature = DEFAULT_T;
      this.nodes.temperature.value = String(DEFAULT_T);
      this.nodes["show-field"].checked = true;
      this.showField = true;

      this.magnetX = PARK_X;
      this.magnetY = PARK_Y;
      this.magnetEnabled = false;
      this.polarity = 1;
      this.dragPointer = null;
      this.canvas.style.cursor = "default";
      this.external.fill(0);
      this.model.initialize(this.nodes["initial-state"].value);
      if (this.model.material === "ferro") {
        // Preserve Python's 20 × 35 zero-temperature preparation steps.
        // Yield to the browser between blocks to keep the interface responsive.
        for (let block = 0; block < 20; block++) {
          for (let s = 0; s < 35; s++) this.model.step(this.external, MODEL_DT, 0);
          await new Promise(resolve => window.requestAnimationFrame(resolve));
        }
      }
      this.model.elapsed = 0;
      this.model.random = new SeededRandom(this.model.seed);
      this.fieldDirty = true;
      this.cachedField = [];
      this.lastTimestamp = null;
      this.accumulator = 0;
      this.lastFieldDraw = -1000;
      this.busy = false;
      this.nodes["loading-panel"].hidden = true;
      this.nodes["experiment-controls"].disabled = false;
      this.updateControls();
      this.draw(performance.now() / 1000);
    } catch (err) { this.reportError(err); }
  }
  requestReset() {
    if (this.busy || this.failed) return;
    this.busy = true;
    void this.resetExperiment();
  }
  updateControls() {
    const labels = {soft: "Soft ferromagnet", hard: "Hard ferromagnet", para: "Paramagnet"};
    this.nodes["initial-state"].disabled = this.model.material === "para";
    this.text("material-badge", labels[this.model.preset]);
    this.text("temperature-value", this.decimal(this.model.temperature));
    this.text("start-pause", this.running ? "Pause" : "Start");
    this.nodes["start-pause"].setAttribute("aria-pressed", String(!this.running));
    this.text("run-label", this.running ? "Simulation running" : "Paused");
    this.nodes["run-dot"].className = this.running ? "status-dot running" : "status-dot paused";
    this.text("toggle-magnet", this.magnetEnabled ? "Disable magnet" : "Enable magnet");
    this.nodes["toggle-magnet"].setAttribute("aria-pressed", String(this.magnetEnabled));
    this.nodes["flip-poles"].hidden = !this.magnetEnabled;
    this.nodes["flip-poles"].disabled = !this.magnetEnabled;
  }
  toggleRunning() {
    if (this.busy || this.failed) return;
    this.running = !this.running;
    this.accumulator = 0;
    this.lastTimestamp = null;
    this.updateControls();
  }
  markFieldChanged() {
    this.fieldDirty = true;
    this.lastFieldDraw = -1000;
    this.updateControls();
  }
  toggleMagnet() {
    if (this.busy || this.failed) return;
    this.magnetEnabled = !this.magnetEnabled;
    this.markFieldChanged();
  }
  flipPoles() {
    if (this.busy || this.failed || !this.magnetEnabled) return;
    this.polarity *= -1;
    this.markFieldChanged();
  }
  onTemperature() {
    this.model.temperature = Number(this.nodes.temperature.value);
    this.updateControls();
  }
  onDisplay() {
    this.showField = this.nodes["show-field"].checked;
    this.lastFieldDraw = -1000;
  }
  eventPoint(event) {
    const rect = this.canvas.getBoundingClientRect();
    return [
      (event.clientX - rect.left) * W / rect.width,
      (event.clientY - rect.top) * H / rect.height,
    ];
  }
  hitMagnet(x, y) {
    return this.magnetEnabled && Math.abs(x - this.magnetX) <= MAGNET_W / 2 + 14 &&
      Math.abs(y - this.magnetY) <= MAGNET_H / 2 + 14;
  }
  onPointerDown(event) {
    if (this.busy || this.failed || this.dragPointer !== null) return;
    if (event.pointerType === "mouse" && event.button !== 0) return;
    const [x, y] = this.eventPoint(event);
    if (this.hitMagnet(x, y)) {
      event.preventDefault();
      this.dragPointer = event.pointerId;
      this.dragOffset = [this.magnetX - x, this.magnetY - y];
      this.canvas.setPointerCapture(this.dragPointer);
      this.canvas.style.cursor = "grabbing";
      this.magnetEnabled = true;
      this.markFieldChanged();
    }
  }
  onPointerMove(event) {
    if (this.busy || this.failed) return;
    const [x, y] = this.eventPoint(event);
    if (this.dragPointer !== null) {
      if (event.pointerId !== this.dragPointer) return;
      event.preventDefault();
      [this.magnetX, this.magnetY] = constrainMagnet(x + this.dragOffset[0], y + this.dragOffset[1]);
      this.markFieldChanged();
    } else {
      this.canvas.style.cursor = this.hitMagnet(x, y) ? "grab" : "default";
    }
  }
  onPointerEnd(event) {
    if (event.pointerId === this.dragPointer) {
      this.dragPointer = null;
      if (this.canvas.hasPointerCapture(event.pointerId)) this.canvas.releasePointerCapture(event.pointerId);
      this.canvas.style.cursor = "grab";
    }
  }
  onVisibility() { this.lastTimestamp = null; this.accumulator = 0; }

  roundedPath(x, y, w, h, radius = 10) {
    const ctx = this.ctx;
    const r = Math.min(radius, w / 2, h / 2);
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.lineTo(x + w - r, y);
    ctx.quadraticCurveTo(x + w, y, x + w, y + r);
    ctx.lineTo(x + w, y + h - r);
    ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
    ctx.lineTo(x + r, y + h);
    ctx.quadraticCurveTo(x, y + h, x, y + h - r);
    ctx.lineTo(x, y + r);
    ctx.quadraticCurveTo(x, y, x + r, y);
    ctx.closePath();
  }
  label(text, x, y, size = 14, color = INK, weight = 400, align = "left") {
    const ctx = this.ctx;
    ctx.font = `${weight} ${size}px system-ui, sans-serif`;
    ctx.fillStyle = color;
    ctx.textAlign = align;
    ctx.textBaseline = "middle";
    ctx.fillText(String(text), x, y);
  }
  refreshFieldView(now) {
    if (now - this.lastFieldDraw < 0.12) return;
    this.lastFieldDraw = now;
    if (!this.showField || !this.magnetEnabled) { this.cachedField = []; return; }
    const xs = [], ys = [], indices = [];
    for (let i = 0; i < this.fieldPixels.length; i++) {
      const [x, y] = this.fieldPixels[i];
      if (Math.abs(x - this.magnetX) > MAGNET_W / 2 + 18 ||
          Math.abs(y - this.magnetY) > MAGNET_H / 2 + 18) {
        xs.push(this.fieldWorldX[i]);
        ys.push(this.fieldWorldY[i]);
        indices.push(i);
      }
    }
    const field = sourceField(xs, ys, this.magnetX, this.magnetY, this.polarity, true);
    this.cachedField = indices.map((id, i) => [
      this.fieldPixels[id][0], this.fieldPixels[id][1], field[2 * i], -field[2 * i + 1],
    ]);
  }
  drawBackground() {
    const ctx = this.ctx;
    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = "#fcfcf8";
    ctx.fillRect(0, 0, W, H);
    ctx.fillStyle = "#e5ece8";
    for (let y = 32; y < H; y += 30) {
      for (let x = 22; x < W; x += 30) ctx.fillRect(x, y, 1, 1);
    }
    ctx.fillStyle = "#ffffff";
    this.roundedPath(PROBE_X - 3, PROBE_Y - 3, PROBE_W + 6, PROBE_H + 6, 10);
    ctx.fill();
    ctx.strokeStyle = "#b9cbc9";
    ctx.lineWidth = 1.4;
    ctx.stroke();
  }
  drawField() {
    const ctx = this.ctx;
    ctx.strokeStyle = FIELD_COLOR;
    ctx.lineWidth = 1.2;
    ctx.globalAlpha = 0.52;
    ctx.beginPath();
    for (const [x, y, bx, by] of this.cachedField) {
      const magnitude = Math.hypot(bx, by);
      if (magnitude < 0.004) continue;
      const length = 26 * (1 - Math.exp(-magnitude / 0.6));
      if (length < 1.5) continue;
      const ux = bx / magnitude;
      const uy = by / magnitude;
      const x1 = x - 0.5 * length * ux;
      const y1 = y - 0.5 * length * uy;
      const x2 = x + 0.5 * length * ux;
      const y2 = y + 0.5 * length * uy;
      const head = Math.min(5, length * 0.34);
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.moveTo(x2 - head * ux + head * 0.48 * uy, y2 - head * uy - head * 0.48 * ux);
      ctx.lineTo(x2, y2);
      ctx.lineTo(x2 - head * ux - head * 0.48 * uy, y2 - head * uy + head * 0.48 * ux);
    }
    ctx.stroke();
    ctx.globalAlpha = 1;
  }
  drawMoments() {
    const ctx = this.ctx;
    const {theta, sx, sy} = this.model;
    for (let i = 0; i < this.model.n; i++) {
      const [x, y] = this.centers[i];
      const bucket = (Math.floor((theta[i] + Math.PI) / TAU * 24) % 24 + 24) % 24;
      ctx.fillStyle = this.palette[bucket];
      ctx.fillRect(x - CELL / 2 + 0.5, y - CELL / 2 + 0.5, CELL - 1, CELL - 1);
    }
    ctx.lineWidth = 3.6;
    ctx.lineCap = "round";
    for (const [color, start, end] of [[SOUTH, -6.4, 0], [NORTH, 0, 6.4]]) {
      ctx.strokeStyle = color;
      ctx.beginPath();
      for (let i = 0; i < this.model.n; i++) {
        const [x, y] = this.centers[i];
        ctx.moveTo(x + start * sx[i], y - start * sy[i]);
        ctx.lineTo(x + end * sx[i], y - end * sy[i]);
      }
      ctx.stroke();
    }
    ctx.fillStyle = NORTH;
    ctx.beginPath();
    for (let i = 0; i < this.model.n; i++) {
      const [x, y] = this.centers[i];
      ctx.moveTo(x + 8.2 * sx[i], y - 8.2 * sy[i]);
      ctx.lineTo(x + 3.7 * sx[i] + 2.7 * sy[i], y - 3.7 * sy[i] + 2.7 * sx[i]);
      ctx.lineTo(x + 3.7 * sx[i] - 2.7 * sy[i], y - 3.7 * sy[i] - 2.7 * sx[i]);
      ctx.closePath();
    }
    ctx.fill();
    ctx.lineCap = "butt";
  }
  drawMagnet() {
    if (!this.magnetEnabled) return;
    const ctx = this.ctx;
    const x = this.magnetX - MAGNET_W / 2;
    const y = this.magnetY - MAGNET_H / 2;
    const [leftColor, leftLabel, rightColor, rightLabel] = this.polarity === 1
      ? [SOUTH, "S", NORTH, "N"]
      : [NORTH, "N", SOUTH, "S"];
    ctx.save();
    this.roundedPath(x, y, MAGNET_W, MAGNET_H, 9);
    ctx.save();
    ctx.clip();
    ctx.fillStyle = leftColor;
    ctx.fillRect(x, y, MAGNET_W / 2, MAGNET_H);
    ctx.fillStyle = rightColor;
    ctx.fillRect(x + MAGNET_W / 2, y, MAGNET_W / 2, MAGNET_H);
    ctx.fillStyle = "rgba(255,255,255,.13)";
    ctx.fillRect(x, y, MAGNET_W, 7);
    ctx.restore();
    ctx.strokeStyle = "#516678";
    ctx.lineWidth = 1.2;
    ctx.stroke();
    this.label(leftLabel, x + MAGNET_W * 0.25, this.magnetY, 21, "white", 750, "center");
    this.label(rightLabel, x + MAGNET_W * 0.75, this.magnetY, 21, "white", 750, "center");
    ctx.restore();
  }
  draw(now) {
    const ratio = Math.min(2, Math.max(1, window.devicePixelRatio || 1));
    if (ratio !== this.pixelRatio) {
      this.pixelRatio = ratio;
      this.canvas.width = Math.round(W * ratio);
      this.canvas.height = Math.round(H * ratio);
    }
    this.ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    this.refreshFieldView(now);
    this.drawBackground();
    this.drawField();
    this.drawMoments();
    this.drawMagnet(); // Last: the bar magnet may overlap the sample.
  }
  animationFrame(timestamp) {
    if (this.failed) return;
    try {
      const stamp = timestamp / 1000;
      const delta = this.lastTimestamp === null ? 0 : Math.max(0, stamp - this.lastTimestamp);
      this.lastTimestamp = stamp;
      if (!this.busy && !document.hidden) {
        if (this.fieldDirty) {
          this.external = sourceField(this.model.positionsX, this.model.positionsY,
            this.magnetX, this.magnetY, this.polarity, this.magnetEnabled);
          this.fieldDirty = false;
        }
        if (this.running) {
          this.accumulator += Math.min(delta, 0.10) * MODEL_TIME_PER_SECOND;
          const started = performance.now();
          let steps = 0;
          while (this.accumulator >= MODEL_DT && steps < MAX_STEPS_PER_FRAME) {
            this.model.step(this.external);
            this.accumulator -= MODEL_DT;
            steps++;
            if (performance.now() - started > 10) break;
          }
        } else {
          this.accumulator = 0;
        }
        if (stamp - this.lastDraw >= 1 / 30) {
          this.draw(performance.now() / 1000);
          this.lastDraw = stamp;
        }
      }
      window.requestAnimationFrame(this.animationFrame);
    } catch (err) { this.reportError(err); }
  }
  reportError(err) {
    console.error(err);
    this.failed = true;
    this.busy = false;
    this.running = false;
    this.nodes["experiment-controls"].disabled = true;
    this.nodes["loading-panel"].hidden = false;
    this.nodes["loading-panel"].classList.add("load-error");
    this.text("loading-title", "The simulation has stopped.");
    this.text("loading-details", "Please check the browser console.");
    this.text("run-label", "Stopped");
    this.nodes["run-dot"].className = "status-dot paused";
  }
}

// Runs without a local server (file://), because all resources are local.
try {
  const APP = new MagnetApplet();
  void APP.start();
} catch (err) {
  console.error(err);
  const panel = document.getElementById("loading-panel");
  if (panel) {
    panel.hidden = false;
    panel.classList.add("load-error");
    document.getElementById("loading-title").textContent = "Could not start the simulation.";
    document.getElementById("loading-details").textContent = String(err);
  }
}
