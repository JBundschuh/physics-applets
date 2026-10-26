"use strict";

/*
 * Rutherford Scattering – interactive physics applet
 *
 * 1. Trajectory view: alpha particles interact with a deliberately scaled
 *    repulsive Coulomb field from eight gold nuclei inside a foil region.
 * 2. Statistics view: scattering angles are sampled using a simplified
 *    impact-parameter model and visualized on a detector and histogram.
 *
 * The numerical and visual scales are educational, not SI-accurate.
 * This is a direct JavaScript adaptation of the reduced PyScript applet.
 */

// -----------------------------------------------------------------------------
// Canvas, browser controls, and simulation state
// -----------------------------------------------------------------------------

const canvas = document.getElementById("simulation-canvas");
const ctx = canvas.getContext("2d");
const W = canvas.width;
const H = canvas.height;

const el = (id) => document.getElementById(id);
const radioValue = (name) => document.querySelector(`input[name="${name}"]:checked`)?.value ?? "";
const checked = (id) => el(id).checked;
const sliderFloat = (id) => Number(el(id).value);
const setText = (id, value) => { el(id).textContent = String(value); };

const state = {
  running: true,
  lastTimestamp: null,
  microEmitAccumulator: 0,
  statsEmitAccumulator: 0,
  particles: [],
  events: [],
  flashes: [],
  total: 0,
  straight: 0,
  light: 0,
  strong: 0,
  back: 0,
  hist: Array(18).fill(0), // 18 angle bins of 10 degrees each.
  lastThetaDeg: 0,
  lastImpact: 0,
  startTime: performance.now() / 1000,
};

// Eight gold nuclei in a staggered 4 × 2 arrangement; distances not to scale.
function makeGoldAtoms() {
  const foilX = Math.trunc(W * 0.63);
  const foilY = 28;
  const foilW = W - foilX - 40;
  const foilH = H - 56;
  const dx = foilW * 0.34;
  const dy = foilH * 0.22;
  const shift = dx * 0.5;
  const startX = foilX + foilW * 0.18;
  const startY = foilY + foilH * 0.18;
  const atoms = [];
  for (let row = 0; row < 4; row++) {
    const y = startY + row * dy;
    const rowShift = (row % 2 === 1) ? shift : 0;
    for (let col = 0; col < 2; col++) {
      atoms.push([startX + rowShift + col * dx, y]);
    }
  }
  return atoms;
}
const GOLD_ATOMS = makeGoldAtoms();

class AlphaParticle {
  constructor(x, y, vx, vy) {
    this.x = x;
    this.y = y;
    this.vx = vx;
    this.vy = vy;
    this.ax = 0;
    this.ay = 0;
    this.trail = [[x, y]];
    this.age = 0;
    this.alive = true;
    this.closestDistance = 1e9;
  }
  addTrailPoint() {
    this.trail.push([this.x, this.y]);
    if (this.trail.length > 95) this.trail.shift();
  }
}

class ScatterEvent {
  constructor(thetaSigned, thetaAbsDeg, impact) {
    this.thetaSigned = thetaSigned;
    this.thetaAbsDeg = thetaAbsDeg;
    this.impact = impact;
    this.age = 0;
    this.life = thetaAbsDeg >= 90 ? 4.2 : thetaAbsDeg >= 30 ? 3.0 : thetaAbsDeg >= 5 ? 1.6 : 0.85;
  }
}

class DetectorFlash {
  constructor(x, y, thetaAbsDeg) {
    this.x = x;
    this.y = y;
    this.thetaAbsDeg = thetaAbsDeg;
    this.age = 0;
    this.life = thetaAbsDeg >= 90 ? 3.8 : thetaAbsDeg >= 30 ? 2.6 : thetaAbsDeg >= 5 ? 1.3 : 0.55;
  }
}

function currentParams() {
  return {
    mode: radioValue("mode"),
    energy: sliderFloat("energy"),
    charge: sliderFloat("charge"),
    rate: sliderFloat("rate"),
    speed: sliderFloat("speed"),
    thickness: sliderFloat("thickness"),
    showTrails: checked("show-trails"),
    showPotential: checked("show-potential"),
    logHistogram: checked("log-histogram"),
  };
}

const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
const length = (x, y) => Math.hypot(x, y);
const degrees = (radians) => radians * 180 / Math.PI;
const radians = (deg) => deg * Math.PI / 180;
const uniform = (min, max) => min + (max - min) * Math.random();

// Box–Muller transform: equivalent normal distribution to random.gauss().
function normalRandom(mean = 0, standardDeviation = 1) {
  let u = 0;
  while (u === 0) u = Math.random();
  const v = Math.random();
  return mean + standardDeviation * Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

function relativeGoldThickness(params) {
  // The 400 nm reference is a didactic scaling, not an SI-calibrated model.
  return Math.max(0.05, params.thickness / 400);
}

function foilBounds() {
  const left = Math.trunc(W * 0.63);
  return [left, left + (W - left - 40)];
}

function inFoilMaterial(x) {
  const [left, right] = foilBounds();
  return left <= x && x <= right;
}

function materialEdgeFactor(x) {
  // Smoothly ramp up the interaction at the two foil boundaries.
  const [left, right] = foilBounds();
  const edge = 18;
  if (x < left || x > right) return 0;
  if (x < left + edge) return (x - left) / edge;
  if (x > right - edge) return (right - x) / edge;
  return 1;
}

// -----------------------------------------------------------------------------
// Canvas drawing primitives
// -----------------------------------------------------------------------------

function drawLine(x1, y1, x2, y2, color = "#000", width = 1, alpha = 1) {
  ctx.save();
  ctx.globalAlpha = alpha;
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.beginPath();
  ctx.moveTo(x1, y1);
  ctx.lineTo(x2, y2);
  ctx.stroke();
  ctx.restore();
}

function drawCircle(x, y, r, fill = "#000", stroke = null, width = 1, alpha = 1) {
  ctx.save();
  ctx.globalAlpha = alpha;
  ctx.beginPath();
  ctx.arc(x, y, r, 0, 2 * Math.PI);
  if (fill !== null) {
    ctx.fillStyle = fill;
    ctx.fill();
  }
  if (stroke !== null) {
    ctx.strokeStyle = stroke;
    ctx.lineWidth = width;
    ctx.stroke();
  }
  ctx.restore();
}

function drawText(text, x, y, size = 14, color = "#172033", align = "left", weight = "400") {
  ctx.save();
  ctx.font = `${weight} ${size}px system-ui, sans-serif`;
  ctx.fillStyle = color;
  ctx.textAlign = align;
  ctx.textBaseline = "middle";
  ctx.fillText(text, x, y);
  ctx.restore();
}

function drawArrow(x1, y1, x2, y2, color = "#1f2937", width = 2, alpha = 1) {
  drawLine(x1, y1, x2, y2, color, width, alpha);
  const angle = Math.atan2(y2 - y1, x2 - x1);
  const size = 9;
  ctx.save();
  ctx.globalAlpha = alpha;
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.moveTo(x2, y2);
  ctx.lineTo(x2 - size * Math.cos(angle - 0.45), y2 - size * Math.sin(angle - 0.45));
  ctx.lineTo(x2 - size * Math.cos(angle + 0.45), y2 - size * Math.sin(angle + 0.45));
  ctx.closePath();
  ctx.fill();
  ctx.restore();
}

function clearCanvas() {
  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = "#fbfcfe";
  ctx.fillRect(0, 0, W, H);
}

// -----------------------------------------------------------------------------
// Rutherford trajectories in the microscopic view
// -----------------------------------------------------------------------------

function spawnMicroParticle(params) {
  // Higher energy results in faster particles and smaller deflections.
  const speed = 230 + 42 * Math.sqrt(params.energy);
  const y = uniform(78, H - 78);
  state.particles.push(new AlphaParticle(36, y, speed, 0));
}

function rutherfordAcceleration(x, y, params) {
  // Scaled Coulomb repulsion acts only within the visible gold foil.
  const materialFactor = materialEdgeFactor(x);
  if (materialFactor <= 0) return [0, 0, 1e9];

  const zAlpha = 2;
  const zTarget = params.charge;
  const kEff = 300;
  const softening = 9; // Prevent numerical singularities.
  let ax = 0;
  let ay = 0;
  let closest = 1e9;

  for (const [gx, gy] of GOLD_ATOMS) {
    const dx = x - gx;
    const dy = y - gy;
    const r2 = dx * dx + dy * dy;
    closest = Math.min(closest, Math.sqrt(r2));
    const rEff = Math.sqrt(r2 + softening * softening);
    // Vector repulsive force: F ∝ Z_alpha * Z_target * r / r_eff^3.
    const factor = materialFactor * kEff * zAlpha * zTarget / (rEff ** 3);
    ax += factor * dx;
    ay += factor * dy;
  }

  const maxA = 3600;
  const acceleration = length(ax, ay);
  if (acceleration > maxA) {
    ax *= maxA / acceleration;
    ay *= maxA / acceleration;
  }
  return [ax, ay, closest];
}

function applyCloseReflection(particle) {
  if (!inFoilMaterial(particle.x)) return;
  for (const [gx, gy] of GOLD_ATOMS) {
    const dx = particle.x - gx;
    const dy = particle.y - gy;
    const r = Math.max(1, Math.sqrt(dx * dx + dy * dy));
    // Retain the source model's short-range reflection rule.
    if (r < 8) {
      const nx = dx / r;
      const ny = dy / r;
      const radialVelocity = particle.vx * nx + particle.vy * ny;
      if (radialVelocity < 0) {
        particle.vx -= 2.15 * radialVelocity * nx;
        particle.vy -= 2.15 * radialVelocity * ny;
        particle.x = gx + nx * 9;
        particle.y = gy + ny * 9;
      }
    }
  }
}

function updateMicro(dt, params) {
  if (!state.running) return;
  state.microEmitAccumulator += params.rate * dt;
  while (state.microEmitAccumulator >= 1) {
    if (state.particles.length < 130) spawnMicroParticle(params);
    state.microEmitAccumulator -= 1;
  }

  for (const particle of state.particles) {
    const [ax, ay, closest] = rutherfordAcceleration(particle.x, particle.y, params);
    particle.ax = ax;
    particle.ay = ay;
    particle.closestDistance = Math.min(particle.closestDistance, closest);
    particle.vx += ax * dt;
    particle.vy += ay * dt;

    // Limit speed to avoid large unphysical canvas jumps.
    const velocity = length(particle.vx, particle.vy);
    if (velocity > 740) {
      particle.vx *= 740 / velocity;
      particle.vy *= 740 / velocity;
    }

    particle.x += particle.vx * dt;
    particle.y += particle.vy * dt;
    particle.age += dt;
    applyCloseReflection(particle);
    particle.addTrailPoint();
    if (particle.x < -130 || particle.x > W + 130 || particle.y < -130 || particle.y > H + 130 || particle.age > 13) {
      particle.alive = false;
    }
  }
  state.particles = state.particles.filter(particle => particle.alive);
}

// -----------------------------------------------------------------------------
// Rutherford angle statistics based on a simplified impact-parameter model
// -----------------------------------------------------------------------------

function sampleImpactParameter(params) {
  const relativeThickness = relativeGoldThickness(params);
  const bMin = 0.055;
  const bMax = 6 / Math.sqrt(relativeThickness);
  // Uniform sampling in area, rather than directly in impact parameter.
  const u = Math.random();
  const b = Math.sqrt(bMin * bMin + u * (bMax * bMax - bMin * bMin));
  const sign = Math.random() < 0.5 ? -1 : 1;
  return sign * b;
}

function sampleRutherfordAngle(params) {
  const relativeThickness = relativeGoldThickness(params);
  const scatterProbability = clamp(0.075 * relativeThickness, 0, 0.32);

  // Most particles pass through with negligible deflection.
  if (Math.random() > scatterProbability) {
    const thetaDeg = clamp(Math.abs(normalRandom(0, 0.6)), 0, 3);
    const sign = Math.random() < 0.5 ? -1 : 1;
    return [radians(sign * thetaDeg), thetaDeg, 99];
  }

  const impact = sampleImpactParameter(params);
  const b = Math.abs(impact);
  // Educational Rutherford-like expression, not an SI computation.
  const c = 1.04 * (params.charge / 79);
  let thetaAbs = 2 * Math.atan(c / (params.energy * b));
  thetaAbs = Math.min(thetaAbs, Math.PI - 0.004);
  const thetaSigned = Math.sign(impact) * thetaAbs;
  return [thetaSigned, degrees(thetaAbs), b];
}

function statsCenter() { return [345, Math.trunc(H * 0.52)]; }
function statsDetectorRadius() { return 235; }

function registerEvent(thetaSigned, thetaAbsDeg, impact) {
  state.total += 1;
  state.lastThetaDeg = thetaAbsDeg;
  state.lastImpact = impact;
  if (thetaAbsDeg < 5) state.straight += 1;
  else if (thetaAbsDeg < 30) state.light += 1;
  else if (thetaAbsDeg < 90) state.strong += 1;
  else state.back += 1;

  const binIndex = Math.trunc(clamp(Math.floor(thetaAbsDeg / 10), 0, state.hist.length - 1));
  state.hist[binIndex] += 1;
  state.events.push(new ScatterEvent(thetaSigned, thetaAbsDeg, impact));
  if (state.events.length > 90) state.events.shift();

  const [cx, cy] = statsCenter();
  const radius = statsDetectorRadius();
  const hitX = cx + radius * Math.cos(thetaSigned);
  const hitY = cy + radius * Math.sin(thetaSigned);
  state.flashes.push(new DetectorFlash(hitX, hitY, thetaAbsDeg));
  if (state.flashes.length > 80) state.flashes.shift();
}

function updateStatistics(dt, params) {
  if (state.running) {
    state.statsEmitAccumulator += params.rate * dt;
    const maxBatch = 8;
    let processed = 0;
    while (state.statsEmitAccumulator >= 1 && processed < maxBatch) {
      const [thetaSigned, thetaAbsDeg, impact] = sampleRutherfordAngle(params);
      registerEvent(thetaSigned, thetaAbsDeg, impact);
      state.statsEmitAccumulator -= 1;
      processed += 1;
    }
  }
  // Match the original: existing detector traces fade even when paused.
  for (const event of state.events) event.age += dt;
  state.events = state.events.filter(event => event.age <= event.life);
  for (const flash of state.flashes) flash.age += dt;
  state.flashes = state.flashes.filter(flash => flash.age <= flash.life);
}

// -----------------------------------------------------------------------------
// Shared drawing functions
// -----------------------------------------------------------------------------

function drawPanelBackground() {
  clearCanvas();
  ctx.save();
  ctx.strokeStyle = "rgba(148, 163, 184, 0.16)";
  ctx.lineWidth = 1;
  for (let x = 0; x <= W; x += 50) {
    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke();
  }
  for (let y = 0; y <= H; y += 50) {
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke();
  }
  ctx.restore();
}

function roundRect(x, y, w, h, r) {
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

function drawBadge(text, x, y, fill = "#eef2ff", stroke = "#c7d2fe", color = "#172033") {
  ctx.save();
  ctx.font = "600 13px system-ui, sans-serif";
  const width = ctx.measureText(text).width + 22;
  const height = 28;
  ctx.fillStyle = fill;
  ctx.strokeStyle = stroke;
  ctx.lineWidth = 1;
  roundRect(x, y, width, height, 10);
  ctx.fill();
  ctx.stroke();
  ctx.fillStyle = color;
  ctx.textBaseline = "middle";
  ctx.fillText(text, x + 11, y + height / 2);
  ctx.restore();
}

// -----------------------------------------------------------------------------
// Trajectory view drawing
// -----------------------------------------------------------------------------

function drawPotentialField() {
  // Colored radial halos indicate field regions, not a calibrated potential map.
  const [foilLeft, foilRight] = foilBounds();
  ctx.save();
  ctx.beginPath();
  ctx.rect(foilLeft, 0, foilRight - foilLeft, H);
  ctx.clip();
  for (const [gx, gy] of GOLD_ATOMS) {
    const radius = 82;
    const gradient = ctx.createRadialGradient(gx, gy, 4, gx, gy, radius);
    gradient.addColorStop(0.00, "rgba(180, 83, 9, 0.42)");
    gradient.addColorStop(0.16, "rgba(234, 179, 8, 0.32)");
    gradient.addColorStop(0.38, "rgba(250, 204, 21, 0.18)");
    gradient.addColorStop(0.70, "rgba(251, 191, 36, 0.08)");
    gradient.addColorStop(1.00, "rgba(251, 191, 36, 0.00)");
    ctx.fillStyle = gradient;
    ctx.beginPath();
    ctx.arc(gx, gy, radius, 0, 2 * Math.PI);
    ctx.fill();
  }
  ctx.restore();
}

function drawMicroSetup() {
  // Alpha source at the left edge.
  ctx.save();
  const grad = ctx.createLinearGradient(0, 0, 96, 0);
  grad.addColorStop(0, "rgba(51, 65, 85, 0.18)");
  grad.addColorStop(1, "rgba(51, 65, 85, 0.02)");
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, 118, H);
  ctx.restore();
  drawText("α source", 34, 38, 15, "#334155", "left", "700");

  // The drawn foil boundaries match the particle interaction region.
  const [foilLeft, foilRight] = foilBounds();
  const foilW = foilRight - foilLeft;
  ctx.save();
  const grad2 = ctx.createLinearGradient(foilLeft, 0, foilRight, 0);
  grad2.addColorStop(0.0, "rgba(245, 158, 11, 0.035)");
  grad2.addColorStop(0.16, "rgba(245, 158, 11, 0.10)");
  grad2.addColorStop(0.50, "rgba(251, 191, 36, 0.14)");
  grad2.addColorStop(0.84, "rgba(245, 158, 11, 0.10)");
  grad2.addColorStop(1.0, "rgba(245, 158, 11, 0.035)");
  ctx.fillStyle = grad2;
  ctx.fillRect(foilLeft, -40, foilW, H + 80);
  drawLine(foilLeft, -30, foilLeft, H + 30, "#b45309", 2.2, 0.36);
  drawLine(foilRight, -30, foilRight, H + 30, "#b45309", 2, 0.26);
  for (const x of [foilLeft + 18, foilLeft + 44, foilLeft + 70, foilLeft + 96]) {
    drawLine(x, 8, x + 18, -12, "#92400e", 1.4, 0.30);
    drawLine(x, H - 8, x + 18, H + 12, "#92400e", 1.4, 0.30);
  }
  ctx.restore();
  drawText("Gold foil", foilLeft + 16, 86, 14, "#92400e", "left", "700");
}

function drawGoldAtoms() {
  for (const [gx, gy] of GOLD_ATOMS) {
    const gradient = ctx.createRadialGradient(gx, gy, 3, gx, gy, 34);
    gradient.addColorStop(0, "rgba(250, 204, 21, 0.24)");
    gradient.addColorStop(1, "rgba(250, 204, 21, 0.030)");
    ctx.save();
    ctx.fillStyle = gradient;
    ctx.beginPath();
    ctx.arc(gx, gy, 35, 0, 2 * Math.PI);
    ctx.fill();
    ctx.strokeStyle = "rgba(180, 83, 9, 0.28)";
    ctx.lineWidth = 1.2;
    ctx.stroke();
    ctx.restore();
    drawCircle(gx, gy, 8.5, "#facc15", "#92400e", 1.5);
    drawCircle(gx - 2, gy - 3, 2.4, "rgba(255,255,255,0.72)");
  }
}

function drawParticles(params) {
  for (const particle of state.particles) {
    if (params.showTrails && particle.trail.length > 1) {
      ctx.save();
      ctx.lineWidth = 2;
      for (let i = 1; i < particle.trail.length; i++) {
        const alpha = i / particle.trail.length;
        ctx.strokeStyle = `rgba(37, 99, 235, ${0.08 + 0.42 * alpha})`;
        ctx.beginPath();
        ctx.moveTo(particle.trail[i - 1][0], particle.trail[i - 1][1]);
        ctx.lineTo(particle.trail[i][0], particle.trail[i][1]);
        ctx.stroke();
      }
      ctx.restore();
    }
    drawCircle(particle.x, particle.y, 4.5, "#2563eb", "#1e40af", 1.2);
    drawText("α", particle.x, particle.y + 0.1, 9, "white", "center", "800");
  }
}

function drawMicroAnnotations() {
  drawBadge("Rutherford model", 18, 18, "#f8fafc", "#cbd5e1");
  drawText("Coulomb repulsion inside the gold foil", W * 0.52, 34, 15, "#7c2d12", "center", "700");
  drawText("Not to scale", W / 2, H - 26, 14, "#64748b", "center");
}

function drawMicro(params) {
  drawPanelBackground();
  if (params.showPotential) drawPotentialField();
  drawMicroSetup();
  drawGoldAtoms();
  drawParticles(params);
  drawMicroAnnotations();
}

// -----------------------------------------------------------------------------
// Scattering statistics view drawing
// -----------------------------------------------------------------------------

function drawStatisticsSetup() {
  const [cx, cy] = statsCenter();
  const radius = statsDetectorRadius();
  ctx.save();
  ctx.fillStyle = "rgba(248, 250, 252, 0.84)";
  ctx.strokeStyle = "rgba(203, 213, 225, 0.9)";
  ctx.lineWidth = 1.5;
  roundRect(22, 70, 610, 512, 18);
  ctx.fill();
  ctx.stroke();
  ctx.restore();
  drawText("Experimental setup", 42, 96, 16, "#334155", "left", "800");
  drawCircle(78, cy, 27, "#334155", "#0f172a", 1.5);
  drawText("α", 78, cy, 19, "#ffffff", "center", "800");
  drawText("Source", 78, cy + 48, 13, "#475569", "center");
  ctx.save();
  ctx.fillStyle = "#475569";
  ctx.fillRect(136, cy - 34, 14, 25);
  ctx.fillRect(136, cy + 9, 14, 25);
  ctx.restore();
  drawText("Collimator", 143, cy + 56, 13, "#475569", "center");
  drawArrow(108, cy, cx - 25, cy, "#2563eb", 2.4, 0.75);
  ctx.save();
  ctx.strokeStyle = "#d97706";
  ctx.lineWidth = 5;
  ctx.beginPath();
  ctx.moveTo(cx, cy - 70);
  ctx.lineTo(cx, cy + 70);
  ctx.stroke();
  ctx.restore();
  drawCircle(cx, cy, 12, "#facc15", "#92400e", 1.5);
  drawText("Gold foil", cx, cy + 92, 13, "#92400e", "center", "700");
  ctx.save();
  ctx.strokeStyle = "rgba(15, 23, 42, 0.35)";
  ctx.lineWidth = 3;
  ctx.setLineDash([9, 7]);
  ctx.beginPath();
  ctx.arc(cx, cy, radius, -Math.PI, Math.PI);
  ctx.stroke();
  ctx.setLineDash([]);
  ctx.restore();
  drawText("Detector screen", cx, cy - radius - 24, 14, "#334155", "center", "700");

  for (const deg of [-150, -90, -30, 0, 30, 90, 150]) {
    const a = radians(deg);
    const x1 = cx + (radius - 8) * Math.cos(a);
    const y1 = cy + (radius - 8) * Math.sin(a);
    const x2 = cx + (radius + 8) * Math.cos(a);
    const y2 = cy + (radius + 8) * Math.sin(a);
    drawLine(x1, y1, x2, y2, "rgba(51, 65, 85, 0.55)", 1.5, 1);
    if ([-90, 0, 90].includes(deg)) {
      const lx = cx + (radius + 28) * Math.cos(a);
      const ly = cy + (radius + 28) * Math.sin(a);
      drawText(deg === 0 ? "0°" : `${Math.abs(deg)}°`, lx, ly, 12, "#64748b", "center");
    }
  }
}

function eventColor(thetaAbsDeg) {
  if (thetaAbsDeg >= 90) return "#dc2626";
  if (thetaAbsDeg >= 30) return "#ea580c";
  if (thetaAbsDeg >= 5) return "#ca8a04";
  return "#2563eb";
}

function drawScatterEvents() {
  const [cx, cy] = statsCenter();
  const radius = statsDetectorRadius();
  for (const event of state.events) {
    const alpha = Math.max(0, 1 - event.age / event.life);
    const color = eventColor(event.thetaAbsDeg);
    drawLine(104, cy, cx, cy, "#2563eb", 1.4, 0.12 * alpha);
    const endX = cx + radius * Math.cos(event.thetaSigned);
    const endY = cy + radius * Math.sin(event.thetaSigned);
    drawLine(cx, cy, endX, endY, color, 2, 0.55 * alpha);
  }
  for (const flash of state.flashes) {
    const alpha = Math.max(0, 1 - flash.age / flash.life);
    const color = eventColor(flash.thetaAbsDeg);
    drawCircle(flash.x, flash.y, 5 + 8 * (1 - alpha), null, color, 2, alpha);
    drawCircle(flash.x, flash.y, 3.5, color, null, 1, alpha);
  }
}

function drawHistogram(params) {
  const x0 = 682;
  const y0 = 96;
  const width = 338;
  const height = 430;
  const padLeft = 44;
  const padBottom = 40;
  const plotX = x0 + padLeft;
  const plotY = y0 + 28;
  const plotW = width - padLeft - 18;
  const plotH = height - padBottom - 48;
  ctx.save();
  ctx.fillStyle = "rgba(255, 255, 255, 0.90)";
  ctx.strokeStyle = "rgba(203, 213, 225, 0.9)";
  ctx.lineWidth = 1.5;
  roundRect(x0, y0, width, height, 18);
  ctx.fill();
  ctx.stroke();
  ctx.restore();
  drawText("Angle histogram", x0 + 18, y0 + 22, 16, "#334155", "left", "800");
  drawText(params.logHistogram ? "logarithmic" : "linear", x0 + width - 18, y0 + 22, 12, "#64748b", "right");
  const counts = state.hist;
  const values = params.logHistogram ? counts.map(count => Math.log10(count + 1)) : [...counts];
  const vmax = Math.max(1e-9, ...values);
  drawLine(plotX, plotY, plotX, plotY + plotH, "#94a3b8", 1.2);
  drawLine(plotX, plotY + plotH, plotX + plotW, plotY + plotH, "#94a3b8", 1.2);
  for (let i = 1; i < 5; i++) {
    const yy = plotY + plotH * (1 - i / 5);
    drawLine(plotX, yy, plotX + plotW, yy, "rgba(148, 163, 184, 0.20)", 1);
  }
  const barGap = 3;
  const barW = (plotW - barGap * (counts.length - 1)) / counts.length;
  for (let i = 0; i < counts.length; i++) {
    const value = values[i];
    const h = value <= 0 ? 0 : plotH * (value / vmax);
    const bx = plotX + i * (barW + barGap);
    const by = plotY + plotH - h;
    const color = i >= 9 ? "#dc2626" : i >= 3 ? "#ea580c" : i >= 1 ? "#ca8a04" : "#2563eb";
    ctx.save();
    ctx.fillStyle = color;
    ctx.globalAlpha = 0.78;
    ctx.fillRect(bx, by, barW, h);
    ctx.restore();
  }
  for (const deg of [0, 30, 60, 90, 120, 150, 180]) {
    const px = plotX + plotW * deg / 180;
    drawLine(px, plotY + plotH, px, plotY + plotH + 5, "#94a3b8", 1);
    drawText(String(deg), px, plotY + plotH + 20, 11, "#64748b", "center");
  }
  drawText("Scattering angle θ", plotX + plotW / 2, y0 + height - 12, 12, "#64748b", "center", "700");
  drawText(`Last angle: ${state.lastThetaDeg.toFixed(1)}°`, x0 + 18, y0 + height + 22, 13, "#334155", "left", "700");
  drawText(`Impact parameter b: ${state.lastImpact.toFixed(2)} a.u.`, x0 + 18, y0 + height + 44, 13, "#64748b", "left");
}

function drawStatisticsAnnotations() {
  drawBadge("Rutherford scattering", 22, 18, "#f8fafc", "#cbd5e1");
  drawBadge("θ = 2 arctan(C/(E·b))", 218, 18, "#fff7ed", "#fed7aa", "#7c2d12");
  drawBadge("Unweighted counts", 462, 18, "#f8fafc", "#cbd5e1", "#334155");
  drawText("Scattering statistics without showing individual foil atoms", W / 2, H - 24, 14, "#64748b", "center");
}

function drawStatistics(params) {
  drawPanelBackground();
  drawStatisticsSetup();
  drawScatterEvents();
  drawHistogram(params);
  drawStatisticsAnnotations();
}

// -----------------------------------------------------------------------------
// UI updates, reset, and animation
// -----------------------------------------------------------------------------

function updateControlVisibility(params) {
  const micro = params.mode === "micro";
  el("micro-options").style.display = micro ? "block" : "none";
  el("stats-options").style.display = micro ? "none" : "block";
  el("count-panel").style.display = micro ? "none" : "block";
}

function updateReadouts(params) {
  updateControlVisibility(params);
  setText("energy-value", params.energy.toFixed(1));
  setText("charge-value", Math.trunc(params.charge));
  setText("rate-value", Math.trunc(params.rate));
  setText("speed-value", Number(params.speed.toPrecision(2)));
  setText("thickness-value", Math.trunc(params.thickness));
  setText("count-total", state.total);
  setText("count-straight", state.straight);
  setText("count-light", state.light);
  setText("count-strong", state.strong);
  setText("count-back", state.back);

  const micro = params.mode === "micro";
  setText("info-text", micro
    ? "Qualitative Coulomb field of gold nuclei inside the foil."
    : "Small impact parameters produce large, rare scattering angles.");

  const runtime = Math.max(0.1, performance.now() / 1000 - state.startTime);
  if (micro) {
    setText("status-line", `Trajectory view · α particles: ${state.particles.length} · Time: ${runtime.toFixed(0)} s`);
  } else {
    setText("status-line", `Statistics · Particles: ${state.total} · Last angle: ${state.lastThetaDeg.toFixed(1)}°`);
  }
}

function resetState() {
  state.microEmitAccumulator = 0;
  state.statsEmitAccumulator = 0;
  state.particles = [];
  state.events = [];
  state.flashes = [];
  state.total = 0;
  state.straight = 0;
  state.light = 0;
  state.strong = 0;
  state.back = 0;
  state.hist = Array(18).fill(0);
  state.lastThetaDeg = 0;
  state.lastImpact = 0;
  state.startTime = performance.now() / 1000;
}

function toggleRunning() {
  state.running = !state.running;
  setText("start-pause", state.running ? "Pause" : "Start");
}

function initializeUI() {
  el("start-pause").addEventListener("click", toggleRunning);
  el("reset").addEventListener("click", resetState);
  // Changing views resets counts and particle histories, as in the source.
  document.querySelectorAll('input[name="mode"]').forEach(node => {
    node.addEventListener("change", resetState);
  });
  setText("status-line", "Simulation ready.");
}

function animationFrame(timestamp) {
  const params = currentParams();
  if (state.lastTimestamp === null) state.lastTimestamp = timestamp;
  const rawDt = (timestamp - state.lastTimestamp) / 1000;
  state.lastTimestamp = timestamp;
  const dt = clamp(rawDt, 0, 0.04) * params.speed;
  if (params.mode === "micro") {
    updateMicro(dt, params);
    drawMicro(params);
  } else {
    updateStatistics(dt, params);
    drawStatistics(params);
  }
  updateReadouts(params);
  window.requestAnimationFrame(animationFrame);
}

initializeUI();
window.requestAnimationFrame(animationFrame);
