"use strict";

/**
 * Heat conduction in a spring–mass grid.
 *
 * A 10 × 10 lattice of moving nodes is connected by springs. Kinetic energy
 * transfers between neighboring nodes through their coupling. Random velocity
 * reorientations approximate disordered thermal motion while preserving the
 * speed of each reoriented node.
 *
 * The model is deliberately qualitative, not an atomistic simulation. All
 * numerical values are dimensionless. Colors and the lower chart represent
 * total mechanical energy (kinetic + spring potential), whereas model
 * temperature is based on kinetic energy alone.
 */

// ---------------------------------------------------------------------------
// DOM and canvas
// ---------------------------------------------------------------------------

const el = (id) => document.getElementById(id);
const floatValue = (id, fallback = 0) => {
  const element = el(id);
  return element ? Number(element.value) : fallback;
};
const intValue = (id, fallback = 0) => Math.trunc(floatValue(id, fallback));
const isChecked = (id) => Boolean(el(id)?.checked);
const setText = (id, value) => {
  const element = el(id);
  if (element) element.textContent = String(value);
};

const simCanvas = el("sim_canvas");
const simCtx = simCanvas.getContext("2d");
const profileCanvas = el("profile_canvas");
const profileCtx = profileCanvas.getContext("2d");

// Cache the stationary guide grid in an offscreen canvas.
const backgroundCanvas = document.createElement("canvas");
const backgroundCtx = backgroundCanvas.getContext("2d");

// ---------------------------------------------------------------------------
// Parameters and simulation state (dimensionless model units)
// ---------------------------------------------------------------------------

const N = 10;
const NODE_COUNT = N * N;
const MASS = 1.0;
const REST_LENGTH = 1.0;
const BASE_DT = 0.004;
const TEMP_TO_V2 = 0.006;

// Weak, invisible restoring springs stabilize the lattice near its rest grid.
// Their linear and nonlinear potential energies are included in total energy.
const PIN_STIFFNESS_FACTOR = 0.80;
const PIN_NONLINEAR_FACTOR = 6.0;

// Direction scattering preserves speed but reduces coherent wave patterns.
const SCATTER_PROBABILITY_PER_SUBSTEP = 0.015;
const TEMP_SMOOTHING = 0.08;
const DIAGNOSTIC_UPDATE_INTERVAL = 8;

// Fixed reference energy per node for blue-to-red coloring. Values above
// this reference use the top color, as in the PyScript version.
const ENERGY_COLOR_REFERENCE = 0.5 * MASS * TEMP_TO_V2 * 120.0;

// Rest positions, current positions, velocities, forces and display values.
let x0 = [];
let y0 = [];
let x = [];
let y = [];
let vx = [];
let vy = [];
let tempSmooth = [];
let ax = [];
let ay = [];
const springPairs = [];

let initialTotalEnergy = 0;
let lastKineticEnergy = 0;
let lastSpringEnergy = 0;
let lastTotalEnergy = 0;
let cachedProfileValues = Array(N).fill(0);
let cachedNodeEnergies = Array(NODE_COUNT).fill(0);
let cachedMeanTemp = 0;
let cachedDeltaTemp = 0;

let isRunning = false;
let frameCounter = 0;

// ---------------------------------------------------------------------------
// Mathematical utilities
// ---------------------------------------------------------------------------

const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
const lerp = (a, b, t) => a + (b - a) * t;
const randomAngle = () => 2 * Math.PI * Math.random();
const temperatureToSpeed = (temp) => Math.sqrt(Math.max(0, temp) * TEMP_TO_V2);
const speedSquaredToTemperature = (v2) => v2 / TEMP_TO_V2;
const currentNodeTemperature = (i) => speedSquaredToTemperature(vx[i] * vx[i] + vy[i] * vy[i]);
const idx = (col, row) => row * N + col;

// Match Python's round-to-even behavior for the integer substep count.
function roundToEven(value) {
  const lower = Math.floor(value);
  const fraction = value - lower;
  if (Math.abs(fraction - 0.5) < 1e-10) {
    return lower % 2 === 0 ? lower : lower + 1;
  }
  return Math.round(value);
}

// ---------------------------------------------------------------------------
// Spring connections and static guide grid
// ---------------------------------------------------------------------------

function buildSpringPairs() {
  for (let row = 0; row < N; row++) {
    for (let col = 0; col < N; col++) {
      const a = idx(col, row);
      if (col < N - 1) springPairs.push([a, idx(col + 1, row)]);
      if (row < N - 1) springPairs.push([a, idx(col, row + 1)]);
    }
  }
}

function screenGeometry() {
  const margin = 74;
  const usable = Math.min(simCanvas.width - 2 * margin, simCanvas.height - 2 * margin);
  const scale = usable / (N - 1);
  const left = (simCanvas.width - usable) / 2;
  const top = (simCanvas.height - usable) / 2 + 12;
  return {left, top, scale};
}

function renderBackgroundGrid() {
  backgroundCanvas.width = simCanvas.width;
  backgroundCanvas.height = simCanvas.height;

  backgroundCtx.clearRect(0, 0, backgroundCanvas.width, backgroundCanvas.height);
  const {left, top, scale} = screenGeometry();

  backgroundCtx.save();
  backgroundCtx.strokeStyle = "rgba(120, 135, 160, 0.13)";
  backgroundCtx.lineWidth = 1;
  backgroundCtx.beginPath();

  for (let row = 0; row < N; row++) {
    const yScreen = top + row * scale;
    backgroundCtx.moveTo(left, yScreen);
    backgroundCtx.lineTo(left + (N - 1) * scale, yScreen);
  }
  for (let col = 0; col < N; col++) {
    const xScreen = left + col * scale;
    backgroundCtx.moveTo(xScreen, top);
    backgroundCtx.lineTo(xScreen, top + (N - 1) * scale);
  }

  backgroundCtx.stroke();
  backgroundCtx.restore();
}

function screenPositionWithGeometry(i, left, top, scale) {
  return [left + x[i] * scale, top + y[i] * scale];
}

// ---------------------------------------------------------------------------
// Initialization and reset
// ---------------------------------------------------------------------------

function targetTemperatureForColumn(col) {
  if (col === 0) return floatValue("temp_left_slider", 100);
  if (col === N - 1) return floatValue("temp_right_slider", 20);
  return floatValue("temp_middle_slider", 20);
}

function initializeLattice() {
  x0 = [];
  y0 = [];
  x = [];
  y = [];
  vx = [];
  vy = [];
  tempSmooth = [];
  ax = Array(NODE_COUNT).fill(0);
  ay = Array(NODE_COUNT).fill(0);

  for (let row = 0; row < N; row++) {
    for (let col = 0; col < N; col++) {
      const gx = col * REST_LENGTH;
      const gy = row * REST_LENGTH;
      x0.push(gx);
      y0.push(gy);
      x.push(gx);
      y.push(gy);

      // Initialize speed from the selected temperature, with a random angle.
      const temp = targetTemperatureForColumn(col);
      const speed = temperatureToSpeed(temp);
      const angle = randomAngle();
      vx.push(speed * Math.cos(angle));
      vy.push(speed * Math.sin(angle));
      tempSmooth.push(temp);
    }
  }

  // Relative energy changes are measured from the current reset state.
  updateDiagnostics();
  initialTotalEnergy = lastTotalEnergy;
  updateLabelsAndStats();
  drawAll(true);
}

// ---------------------------------------------------------------------------
// Mechanical forces, energies and numerical time integration
// ---------------------------------------------------------------------------

const stiffness = () => floatValue("stiffness_slider", 5.0);

function clearAccelerations() {
  for (let i = 0; i < NODE_COUNT; i++) {
    ax[i] = 0;
    ay[i] = 0;
  }
}

function addSpringForce(a, b, restLength, k) {
  const dx = x[b] - x[a];
  const dy = y[b] - y[a];
  const dist = Math.sqrt(dx * dx + dy * dy);
  if (dist < 1e-9) return;

  const extension = dist - restLength;
  const forceMagnitude = k * extension;
  const fx = forceMagnitude * dx / dist;
  const fy = forceMagnitude * dy / dist;

  ax[a] += fx / MASS;
  ay[a] += fy / MASS;
  ax[b] -= fx / MASS;
  ay[b] -= fy / MASS;
}

function computeForces() {
  clearAccelerations();
  const k = stiffness();
  const kPin = PIN_STIFFNESS_FACTOR * k;

  // Visible springs connect horizontal and vertical nearest neighbors.
  for (const [a, b] of springPairs) {
    addSpringForce(a, b, REST_LENGTH, k);
  }

  // Invisible nonlinear restoring springs act on each node's rest position.
  for (let i = 0; i < NODE_COUNT; i++) {
    const dx = x[i] - x0[i];
    const dy = y[i] - y0[i];
    const r2 = dx * dx + dy * dy;
    const nonlinearFactor = 1 + PIN_NONLINEAR_FACTOR * r2;
    ax[i] += -kPin * nonlinearFactor * dx / MASS;
    ay[i] += -kPin * nonlinearFactor * dy / MASS;
  }
}

function computeSpringEnergyOnly(energyByCol = null, energyByNode = null) {
  const k = stiffness();
  const kPin = PIN_STIFFNESS_FACTOR * k;
  let energy = 0;

  // Share each neighboring spring's energy equally between its two ends.
  for (const [a, b] of springPairs) {
    const dx = x[b] - x[a];
    const dy = y[b] - y[a];
    const dist = Math.sqrt(dx * dx + dy * dy);
    const extension = dist - REST_LENGTH;
    const springEnergy = 0.5 * k * extension * extension;
    energy += springEnergy;
    if (energyByCol) {
      energyByCol[a % N] += 0.5 * springEnergy;
      energyByCol[b % N] += 0.5 * springEnergy;
    }
    if (energyByNode) {
      energyByNode[a] += 0.5 * springEnergy;
      energyByNode[b] += 0.5 * springEnergy;
    }
  }

  // Attribute restoring-spring energy entirely to its own node and column.
  for (let i = 0; i < NODE_COUNT; i++) {
    const dx = x[i] - x0[i];
    const dy = y[i] - y0[i];
    const r2 = dx * dx + dy * dy;
    const pinEnergy = 0.5 * kPin * r2 + 0.25 * kPin * PIN_NONLINEAR_FACTOR * r2 * r2;
    energy += pinEnergy;
    if (energyByCol) energyByCol[i % N] += pinEnergy;
    if (energyByNode) energyByNode[i] += pinEnergy;
  }
  return energy;
}

function scatterVelocityDirections() {
  for (let i = 0; i < NODE_COUNT; i++) {
    if (Math.random() < SCATTER_PROBABILITY_PER_SUBSTEP) {
      const speed = Math.sqrt(vx[i] * vx[i] + vy[i] * vy[i]);
      const angle = randomAngle();
      vx[i] = speed * Math.cos(angle);
      vy[i] = speed * Math.sin(angle);
    }
  }
}

function applyBoundaryThermostats() {
  if (!isChecked("thermostat_checkbox")) return;

  const leftTemp = floatValue("temp_left_slider", 100);
  const rightTemp = floatValue("temp_right_slider", 20);

  // Rescale boundary speeds only. Positions and spring coupling stay free.
  for (let row = 0; row < N; row++) {
    for (const [col, targetTemp] of [[0, leftTemp], [N - 1, rightTemp]]) {
      const i = idx(col, row);
      const targetV2 = Math.max(0, targetTemp) * TEMP_TO_V2;
      const currentV2 = vx[i] * vx[i] + vy[i] * vy[i];
      if (currentV2 > 1e-12) {
        const scale = Math.sqrt(targetV2 / currentV2);
        vx[i] *= scale;
        vy[i] *= scale;
      } else {
        const speed = Math.sqrt(targetV2);
        const angle = randomAngle();
        vx[i] = speed * Math.cos(angle);
        vy[i] = speed * Math.sin(angle);
      }
      tempSmooth[i] = 0.85 * tempSmooth[i] + 0.15 * targetTemp;
    }
  }
}

function updateTemperatureSmoothing() {
  for (let i = 0; i < NODE_COUNT; i++) {
    const currentTemp = currentNodeTemperature(i);
    tempSmooth[i] = (1 - TEMP_SMOOTHING) * tempSmooth[i] + TEMP_SMOOTHING * currentTemp;
  }
}

function singlePhysicsStep(dt) {
  // Symplectic Euler: velocity update first, position update second.
  computeForces();
  for (let i = 0; i < NODE_COUNT; i++) {
    vx[i] += ax[i] * dt;
    vy[i] += ay[i] * dt;
    x[i] += vx[i] * dt;
    y[i] += vy[i] * dt;
  }
  scatterVelocityDirections();
  applyBoundaryThermostats();
  updateTemperatureSmoothing();
}

function advanceSimulation(visualSteps = 1) {
  const speed = floatValue("speed_slider", 1);
  // Increase the number of stable substeps, not the integration time step.
  const substepsPerVisualStep = Math.max(1, roundToEven(3 * speed));
  for (let step = 0; step < visualSteps * substepsPerVisualStep; step++) {
    singlePhysicsStep(BASE_DT);
  }
}

// ---------------------------------------------------------------------------
// Statistics and column energy profile
// ---------------------------------------------------------------------------

function columnAverageTemperatures() {
  const values = [];
  for (let col = 0; col < N; col++) {
    let total = 0;
    for (let row = 0; row < N; row++) {
      total += tempSmooth[idx(col, row)];
    }
    values.push(total / N);
  }
  return values;
}

function meanModelTemperature() {
  let total = 0;
  for (let i = 0; i < NODE_COUNT; i++) {
    total += currentNodeTemperature(i);
  }
  return total / NODE_COUNT;
}

function updateDiagnostics() {
  const columnTemps = columnAverageTemperatures();
  cachedMeanTemp = meanModelTemperature();
  cachedDeltaTemp = Math.max(...columnTemps) - Math.min(...columnTemps);

  cachedProfileValues = Array(N).fill(0);
  cachedNodeEnergies = Array(NODE_COUNT).fill(0);
  let kinetic = 0;
  for (let i = 0; i < NODE_COUNT; i++) {
    const nodeEnergy = 0.5 * MASS * (vx[i] * vx[i] + vy[i] * vy[i]);
    kinetic += nodeEnergy;
    cachedNodeEnergies[i] = nodeEnergy;
    cachedProfileValues[i % N] += nodeEnergy;
  }

  const spring = computeSpringEnergyOnly(cachedProfileValues, cachedNodeEnergies);
  lastKineticEnergy = kinetic;
  lastSpringEnergy = spring;
  lastTotalEnergy = kinetic + spring;
}

// ---------------------------------------------------------------------------
// Energy colors and canvas drawing
// ---------------------------------------------------------------------------

function energyColor(energy) {
  const t = clamp(energy / ENERGY_COLOR_REFERENCE, 0, 1);
  const cold = [45, 100, 220];
  const mid = [240, 246, 255];
  const hot = [230, 80, 25];
  const from = t < 0.5 ? cold : mid;
  const to = t < 0.5 ? mid : hot;
  const u = t < 0.5 ? t / 0.5 : (t - 0.5) / 0.5;
  const r = Math.trunc(lerp(from[0], to[0], u));
  const g = Math.trunc(lerp(from[1], to[1], u));
  const b = Math.trunc(lerp(from[2], to[2], u));
  return `rgb(${r},${g},${b})`;
}

function clearCanvas(ctx, canvas) {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
}

function drawSimulation() {
  clearCanvas(simCtx, simCanvas);
  simCtx.drawImage(backgroundCanvas, 0, 0);
  const {left, top, scale} = screenGeometry();
  drawSprings(left, top, scale);
  drawNodes(left, top, scale);
  drawSimulationLabels();
}

function drawSprings(left, top, scale) {
  simCtx.save();
  simCtx.strokeStyle = "rgba(60, 75, 100, 0.35)";
  simCtx.lineWidth = 1.3;
  simCtx.beginPath();
  for (const [a, b] of springPairs) {
    const [axScreen, ayScreen] = screenPositionWithGeometry(a, left, top, scale);
    const [bxScreen, byScreen] = screenPositionWithGeometry(b, left, top, scale);
    simCtx.moveTo(axScreen, ayScreen);
    simCtx.lineTo(bxScreen, byScreen);
  }
  simCtx.stroke();
  simCtx.restore();
}

function drawNodes(left, top, scale) {
  for (let row = 0; row < N; row++) {
    for (let col = 0; col < N; col++) {
      const i = idx(col, row);
      const [sx, sy] = screenPositionWithGeometry(i, left, top, scale);
      const energy = cachedNodeEnergies[i];
      const radius = 7.5;
      const boundary = col === 0 || col === N - 1;
      const borderWidth = boundary ? 2.3 : 1.2;
      const borderColor = boundary ? "rgba(30, 40, 70, 0.75)" : "rgba(30, 40, 70, 0.45)";

      simCtx.beginPath();
      simCtx.arc(sx, sy, radius, 0, 2 * Math.PI);
      simCtx.fillStyle = energyColor(energy);
      simCtx.fill();
      simCtx.lineWidth = borderWidth;
      simCtx.strokeStyle = borderColor;
      simCtx.stroke();
    }
  }
}

function drawSimulationLabels() {
  simCtx.save();
  simCtx.font = "14px system-ui, sans-serif";
  if (isChecked("thermostat_checkbox")) {
    simCtx.fillStyle = "rgba(194, 65, 12, 0.95)";
    simCtx.fillText("Heat baths: boundary temperatures fixed", 26, 58);
  } else {
    simCtx.fillStyle = "rgba(47, 109, 246, 0.95)";
    simCtx.fillText("Closed grid: energy approximately conserved", 26, 58);
  }
  simCtx.restore();
}

function drawProfile() {
  clearCanvas(profileCtx, profileCanvas);
  const values = cachedProfileValues;
  const width = profileCanvas.width;
  const height = profileCanvas.height;
  const marginLeft = 54;
  const marginRight = 26;
  const marginTop = 24;
  const marginBottom = 42;
  const plotW = width - marginLeft - marginRight;
  const plotH = height - marginTop - marginBottom;
  const maxEnergy = Math.max(1, Math.max(...values) * 1.15);

  profileCtx.save();
  profileCtx.strokeStyle = "rgba(120, 135, 160, 0.25)";
  profileCtx.lineWidth = 1;
  profileCtx.beginPath();
  for (const frac of [0, 0.25, 0.5, 0.75, 1]) {
    const yGrid = marginTop + plotH * (1 - frac);
    profileCtx.moveTo(marginLeft, yGrid);
    profileCtx.lineTo(marginLeft + plotW, yGrid);
  }
  profileCtx.stroke();

  profileCtx.strokeStyle = "rgba(30, 40, 70, 0.55)";
  profileCtx.beginPath();
  profileCtx.moveTo(marginLeft, marginTop);
  profileCtx.lineTo(marginLeft, marginTop + plotH);
  profileCtx.lineTo(marginLeft + plotW, marginTop + plotH);
  profileCtx.stroke();

  const points = [];
  for (let col = 0; col < N; col++) {
    const energy = values[col];
    const xp = marginLeft + plotW * col / (N - 1);
    const yp = marginTop + plotH * (1 - clamp(energy / maxEnergy, 0, 1));
    points.push([xp, yp]);
  }

  profileCtx.strokeStyle = "#2f6df6";
  profileCtx.lineWidth = 2.4;
  profileCtx.beginPath();
  for (let p = 0; p < points.length; p++) {
    const [xp, yp] = points[p];
    if (p === 0) profileCtx.moveTo(xp, yp);
    else profileCtx.lineTo(xp, yp);
  }
  profileCtx.stroke();

  for (let p = 0; p < points.length; p++) {
    const [xp, yp] = points[p];
    profileCtx.beginPath();
    profileCtx.arc(xp, yp, 5.5, 0, 2 * Math.PI);
    // Use the mean energy per node of this column for its point color.
    profileCtx.fillStyle = energyColor(values[p] / N);
    profileCtx.fill();
    profileCtx.strokeStyle = "rgba(30, 40, 70, 0.55)";
    profileCtx.lineWidth = 1;
    profileCtx.stroke();
  }

  profileCtx.fillStyle = "#657086";
  profileCtx.font = "13px system-ui, sans-serif";
  profileCtx.fillText("Column", width / 2 - 23, height - 9);
  profileCtx.fillText("E", 20, marginTop - 9);
  profileCtx.fillText(maxEnergy.toFixed(1), 10, marginTop + 5);
  profileCtx.fillText("0", 35, marginTop + plotH + 5);
  profileCtx.fillText("1", marginLeft - 3, height - 19);
  profileCtx.fillText(String(N), marginLeft + plotW - 8, height - 19);
  profileCtx.restore();
}

function drawAll(forceProfile = false) {
  drawSimulation();
  if (forceProfile) drawProfile();
}

// ---------------------------------------------------------------------------
// Controls and animation loop
// ---------------------------------------------------------------------------

function updateSliderLabelsOnly() {
  setText("speed_value", `${floatValue("speed_slider", 1).toFixed(2)}×`);
  setText("stiffness_value", floatValue("stiffness_slider", 5).toFixed(2));
  setText("temp_left_value", String(intValue("temp_left_slider", 100)));
  setText("temp_middle_value", String(intValue("temp_middle_slider", 20)));
  setText("temp_right_value", String(intValue("temp_right_slider", 20)));
  setText("status_text", isRunning ? "Running" : "Paused");
  setText("play_button", isRunning ? "⏸ Pause" : "▶ Start");
}

function updateLabelsAndStats() {
  updateSliderLabelsOnly();
  setText("mean_temp_value", cachedMeanTemp.toFixed(1));
  setText("delta_temp_value", cachedDeltaTemp.toFixed(1));
  setText("kin_energy_value", lastKineticEnergy.toFixed(3));
  setText("spring_energy_value", lastSpringEnergy.toFixed(3));
  setText("total_energy_value", lastTotalEnergy.toFixed(3));
  if (initialTotalEnergy > 1e-12) {
    const drift = 100 * (lastTotalEnergy - initialTotalEnergy) / initialTotalEnergy;
    setText("energy_drift_value", `${drift >= 0 ? "+" : ""}${drift.toFixed(2)} %`);
  } else {
    setText("energy_drift_value", "–");
  }
}

function togglePlay() {
  isRunning = !isRunning;
  updateSliderLabelsOnly();
}

function resetSimulation() {
  isRunning = false;
  frameCounter = 0;
  initializeLattice();
}

function onInput() {
  updateDiagnostics();
  updateLabelsAndStats();
  drawAll(true);
}

function onTemperatureInput() {
  if (!isRunning) initializeLattice();
  else updateSliderLabelsOnly();
}

function onStiffnessInput() {
  updateDiagnostics();
  if (!isRunning) initialTotalEnergy = lastTotalEnergy;
  updateLabelsAndStats();
  drawAll(true);
}

function animationLoop() {
  if (isRunning) {
    advanceSimulation(1);
    frameCounter++;
    if (frameCounter % DIAGNOSTIC_UPDATE_INTERVAL === 0) {
      updateDiagnostics();
      updateLabelsAndStats();
      drawAll(true);
    } else {
      drawAll(false);
    }
  }
  requestAnimationFrame(animationLoop);
}

buildSpringPairs();
renderBackgroundGrid();

el("play_button").addEventListener("click", togglePlay);
el("reset_button").addEventListener("click", resetSimulation);
el("speed_slider").addEventListener("input", onInput);
for (const id of ["temp_left_slider", "temp_middle_slider", "temp_right_slider"]) {
  el(id).addEventListener("input", onTemperatureInput);
}
el("stiffness_slider").addEventListener("input", onStiffnessInput);
el("thermostat_checkbox").addEventListener("change", onInput);

initializeLattice();
requestAnimationFrame(animationLoop);
