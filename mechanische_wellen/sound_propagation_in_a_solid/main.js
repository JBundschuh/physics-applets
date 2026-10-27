"use strict";

/*
 * Longitudinal sound propagation in a solid — spring–mass column model.
 *
 * The visible 2D grid represents material layers. All points within one
 * column share the same longitudinal displacement u[j]. The model solves
 *
 *     m * u''[j] = k * (u[j+1] - 2*u[j] + u[j-1]).
 *
 * No transverse motion, diagonal springs, thermal motion, or additional
 * stabilization is included. Node brightness encodes local mechanical energy:
 * kinetic energy plus half the energy of each adjacent spring.
 *
 * The optional continuum solution is calculated independently, including the
 * first reflection at the right boundary. It is not interpolated from the grid.
 */

// DOM helpers
const el = (id) => document.getElementById(id);
const number = (id, fallback) => el(id) ? Number(el(id).value) : fallback;
const checked = (id) => el(id)?.checked ?? false;
const setText = (id, value) => {
  const element = el(id);
  if (element) element.textContent = String(value);
};

// Model parameters and state (unchanged from the PyScript version).
const COLS = 25;
const ROWS = 8;
const SPACING = 1.0;
const BASE_DT = 0.006;
const PULSE_DURATION = 1.60;
const ENERGY_DISPLAY_REFERENCE = 0.14;

const u = Array(COLS).fill(0.0);
const v = Array(COLS).fill(0.0);
const acc = Array(COLS).fill(0.0);

let modelTime = 0.0;
let isRunning = false;
let lastTimestamp = null;
let accumulator = 0.0;

let pulseStart = null;
let pulseAmplitude = 0.30;
let driverPhaseStart = 0.0;
let driverWasActive = false;

let currentK = 4.0;
let currentM = 1.0;
let currentSpeed = 1.0;
let currentBoundary = "absorbing";
let currentFrequency = 0.20;

const simCanvas = el("sim_canvas");
const profileCanvas = el("profile_canvas");
const simCtx = simCanvas.getContext("2d");
const profileCtx = profileCanvas.getContext("2d");

function readParameters() {
  currentK = number("stiffness_slider", 4.0);
  currentM = number("mass_slider", 1.0);
  currentSpeed = number("speed_slider", 1.0);
  currentFrequency = number("frequency_slider", 0.20);
  currentBoundary = el("boundary_select")?.value ?? "absorbing";
}

// Source excitation and spring–mass dynamics
function raisedCosinePulse(localTime, amplitude) {
  // Smooth out-and-back pulse; displacement and velocity vanish at both ends.
  if (localTime < 0.0 || localTime > PULSE_DURATION) return [0.0, 0.0];
  const phase = 2.0 * Math.PI * localTime / PULSE_DURATION;
  const displacement = 0.5 * amplitude * (1.0 - Math.cos(phase));
  const velocity = amplitude * Math.PI / PULSE_DURATION * Math.sin(phase);
  return [displacement, velocity];
}

function sourceState(timeValue) {
  // Prescribed motion of the leftmost material layer.
  if (checked("driver_checkbox")) {
    const phaseTime = timeValue - driverPhaseStart;
    if (phaseTime < 0.0) return [0.0, 0.0];
    const omega = 2.0 * Math.PI * currentFrequency;
    const amplitude = number("amplitude_slider", 0.30) * 0.55;
    return [
      amplitude * Math.sin(omega * phaseTime),
      amplitude * omega * Math.cos(omega * phaseTime),
    ];
  }

  if (pulseStart !== null) {
    return raisedCosinePulse(timeValue - pulseStart, pulseAmplitude);
  }
  return [0.0, 0.0];
}

function calculateAcceleration(timeValue) {
  const [sourceU, sourceV] = sourceState(timeValue);
  u[0] = sourceU;
  v[0] = sourceV;
  acc[0] = 0.0;

  const factor = currentK / currentM;
  for (let j = 1; j < COLS - 1; j++) {
    acc[j] = factor * (u[j + 1] - 2.0 * u[j] + u[j - 1]);
  }

  const last = COLS - 1;
  if (currentBoundary === "fixed") {
    acc[last] = 0.0;
  } else if (currentBoundary === "absorbing") {
    // Impedance-matched damper at the right edge: Z = sqrt(k*m).
    const damping = Math.sqrt(currentK * currentM);
    acc[last] = (currentK * (u[last - 1] - u[last]) - damping * v[last]) / currentM;
  } else {
    // Free end: no additional spring to the right.
    acc[last] = factor * (u[last - 1] - u[last]);
  }
}

function physicsStep(dt) {
  // Symplectic Euler integration, using exactly the original fixed timestep.
  calculateAcceleration(modelTime);
  for (let j = 1; j < COLS; j++) {
    v[j] += acc[j] * dt;
    u[j] += v[j] * dt;
  }
  if (currentBoundary === "fixed") {
    u[COLS - 1] = 0.0;
    v[COLS - 1] = 0.0;
  }
  modelTime += dt;
  const [sourceU, sourceV] = sourceState(modelTime);
  u[0] = sourceU;
  v[0] = sourceV;
}

function localEnergies() {
  // Attribute half of each spring's potential energy to each end column.
  const energies = v.map(velocity => 0.5 * currentM * velocity * velocity);
  let springTotal = 0.0;
  for (let j = 0; j < COLS - 1; j++) {
    const springEnergy = 0.5 * currentK * (u[j + 1] - u[j]) ** 2;
    springTotal += springEnergy;
    energies[j] += 0.5 * springEnergy;
    energies[j + 1] += 0.5 * springEnergy;
  }
  const kineticTotal = 0.5 * currentM * v.reduce((sum, velocity) => sum + velocity * velocity, 0);
  return [energies, kineticTotal, springTotal];
}

// Canvas rendering
function geometry(canvas) {
  const width = canvas.width;
  const height = canvas.height;
  const left = 62.0;
  const right = width - 44.0;
  const top = 62.0;
  const bottom = height - 54.0;
  const dx = (right - left) / (COLS - 1);
  const dy = (bottom - top) / (ROWS - 1);
  return [width, height, left, right, top, bottom, dx, dy];
}

function drawSimulation() {
  const ctx = simCtx;
  const [width, height, left, right, top, bottom, dx, dy] = geometry(simCanvas);
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#fbfcfe";
  ctx.fillRect(0, 0, width, height);

  // Dashed rest positions: each column can move longitudinally only.
  ctx.strokeStyle = "#e4e8ef";
  ctx.lineWidth = 1;
  ctx.setLineDash([3, 5]);
  for (let j = 0; j < COLS; j++) {
    const restX = left + j * dx;
    ctx.beginPath();
    ctx.moveTo(restX, top - 13);
    ctx.lineTo(restX, bottom + 13);
    ctx.stroke();
  }
  ctx.setLineDash([]);

  const [energies] = localEnergies();
  // Allow room for approximately doubled displacement at a free-end reflection.
  const amplitudeScale = 0.34 * dx / Math.max(0.30, number("amplitude_slider", 0.30));
  const xs = u.map((displacement, j) => left + j * dx + amplitudeScale * displacement);

  // Horizontal links represent springs; vertical links are visual only.
  ctx.strokeStyle = "#aeb7c5";
  ctx.lineWidth = 1.15;
  for (let row = 0; row < ROWS; row++) {
    const yPos = top + row * dy;
    ctx.beginPath();
    ctx.moveTo(xs[0], yPos);
    for (let j = 1; j < COLS; j++) ctx.lineTo(xs[j], yPos);
    ctx.stroke();
  }

  ctx.strokeStyle = "#d3d8e1";
  ctx.lineWidth = 1;
  for (let j = 0; j < COLS; j++) {
    ctx.beginPath();
    ctx.moveTo(xs[j], top);
    ctx.lineTo(xs[j], bottom);
    ctx.stroke();
  }

  const maxEnergy = Math.max(...energies, ENERGY_DISPLAY_REFERENCE);
  for (let j = 0; j < COLS; j++) {
    const intensity = Math.min(1.0, Math.sqrt(energies[j] / maxEnergy));
    const grey = Math.round(220 - 185 * intensity);
    ctx.fillStyle = `rgb(${grey},${grey},${grey})`;
    for (let row = 0; row < ROWS; row++) {
      const yPos = top + row * dy;
      ctx.beginPath();
      ctx.arc(xs[j], yPos, 5.1, 0, 2 * Math.PI);
      ctx.fill();
    }
  }

  ctx.fillStyle = "#68758a";
  ctx.font = "13px system-ui, sans-serif";
  ctx.textAlign = "left";
  ctx.fillText("Excitation", left - 16, 29);
  ctx.textAlign = "right";
  const endings = {free: "Free end", fixed: "Fixed end", absorbing: "Absorbing end"};
  ctx.fillText(endings[currentBoundary], right + 15, 29);
}

function continuumValue(xPosition) {
  // Independent continuum wave approximation with the first reflection only.
  // Fixed end: displacement is inverted. Free end: same sign.
  // Absorbing end: incident wave only. No reflection at the left source.
  const waveSpeed = SPACING * Math.sqrt(currentK / currentM);
  const length = (COLS - 1) * SPACING;
  const incidentTime = modelTime - xPosition / waveSpeed;
  const incident = sourceState(incidentTime)[0];
  if (currentBoundary === "absorbing") return incident;

  const reflectedTime = modelTime - (2.0 * length - xPosition) / waveSpeed;
  const reflected = sourceState(reflectedTime)[0];
  const reflectionSign = currentBoundary === "fixed" ? -1.0 : 1.0;
  return incident + reflectionSign * reflected;
}

function drawProfile() {
  const ctx = profileCtx;
  const width = profileCanvas.width;
  const height = profileCanvas.height;
  const left = 58.0;
  const right = width - 28.0;
  const top = 28.0;
  const bottom = height - 42.0;
  const mid = 0.5 * (top + bottom);
  const xScale = (right - left) / (COLS - 1);
  const amplitude = Math.max(0.30, number("amplitude_slider", 0.30));
  const yScale = 0.22 * (bottom - top) / amplitude;

  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#fbfcfe";
  ctx.fillRect(0, 0, width, height);
  ctx.strokeStyle = "#d7dde7";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(left, mid);
  ctx.lineTo(right, mid);
  ctx.stroke();

  ctx.fillStyle = "#68758a";
  ctx.font = "12px system-ui, sans-serif";
  ctx.textAlign = "right";
  ctx.fillText("0", left - 9, mid + 4);
  ctx.textAlign = "center";
  ctx.fillText("Position in the solid", 0.5 * (left + right), height - 13);

  if (checked("continuum_checkbox")) {
    ctx.strokeStyle = "#8a94a5";
    ctx.lineWidth = 2.2;
    ctx.setLineDash([8, 6]);
    ctx.beginPath();
    const sampleCount = 240;
    for (let sample = 0; sample < sampleCount; sample++) {
      const fraction = sample / (sampleCount - 1);
      const xModel = fraction * (COLS - 1) * SPACING;
      const px = left + fraction * (right - left);
      const py = mid - yScale * continuumValue(xModel);
      if (sample === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    }
    ctx.stroke();
    ctx.setLineDash([]);
  }

  ctx.strokeStyle = "#202632";
  ctx.lineWidth = 2.4;
  ctx.beginPath();
  for (let j = 0; j < COLS; j++) {
    const px = left + j * xScale;
    const py = mid - yScale * u[j];
    if (j === 0) ctx.moveTo(px, py);
    else ctx.lineTo(px, py);
  }
  ctx.stroke();

  ctx.fillStyle = "#202632";
  for (let j = 0; j < COLS; j++) {
    ctx.beginPath();
    ctx.arc(left + j * xScale, mid - yScale * u[j], 2.7, 0, 2 * Math.PI);
    ctx.fill();
  }
}

function drawAll() {
  drawSimulation();
  drawProfile();
  setText("time_value", modelTime.toFixed(2));
}

// Controls and frame loop
function resetState() {
  u.fill(0.0);
  v.fill(0.0);
  acc.fill(0.0);
  modelTime = 0.0;
  pulseStart = null;
  driverPhaseStart = 0.0;
  lastTimestamp = null;
  accumulator = 0.0;
  setText("status_text", isRunning ? "Running" : "Ready");
  drawAll();
}

function sendPulse() {
  pulseStart = modelTime;
  pulseAmplitude = number("amplitude_slider", 0.30);
  isRunning = true;
  lastTimestamp = null;
  setText("status_text", "Pulse running");
  setText("play_button", "Ⅱ Pause");
}

function togglePlay() {
  isRunning = !isRunning;
  lastTimestamp = null;
  setText("play_button", isRunning ? "Ⅱ Pause" : "▶ Start");
  setText("status_text", isRunning ? "Running" : "Paused");
}

function onParameterChange() {
  readParameters();
  setText("stiffness_value", currentK.toFixed(1));
  setText("mass_value", currentM.toFixed(1));
  setText("amplitude_value", number("amplitude_slider", 0.30).toFixed(2));
  setText("speed_value", `${currentSpeed.toFixed(2)}×`);
  setText("frequency_value", currentFrequency.toFixed(2));
  const legend = el("continuum_legend");
  if (legend) legend.hidden = !checked("continuum_checkbox");
  drawAll();
}

function onDriverChange() {
  const active = checked("driver_checkbox");
  if (active && !driverWasActive) {
    driverPhaseStart = modelTime;
    pulseStart = null;
    isRunning = true;
    lastTimestamp = null;
    setText("play_button", "Ⅱ Pause");
    setText("status_text", "Signal generator");
  }
  driverWasActive = active;
  onParameterChange();
}

function animationFrame(timestamp) {
  readParameters();
  if (lastTimestamp === null) lastTimestamp = timestamp;
  const elapsed = Math.min(0.05, Math.max(0.0, (timestamp - lastTimestamp) / 1000.0));
  lastTimestamp = timestamp;

  if (isRunning) {
    // Integrate at fixed model steps; speed scales the accumulated model time.
    accumulator += elapsed * currentSpeed;
    let steps = 0;
    while (accumulator >= BASE_DT && steps < 40) {
      physicsStep(BASE_DT);
      accumulator -= BASE_DT;
      steps++;
    }
    if (pulseStart !== null && modelTime > pulseStart + PULSE_DURATION && !checked("driver_checkbox")) {
      setText("status_text", "Running");
    }
  }
  drawAll();
  window.requestAnimationFrame(animationFrame);
}

function bind(id, eventName, handler) {
  const element = el(id);
  if (element) element.addEventListener(eventName, handler);
}

bind("pulse_button", "click", sendPulse);
bind("play_button", "click", togglePlay);
bind("reset_button", "click", resetState);
for (const id of ["stiffness_slider", "mass_slider", "amplitude_slider", "speed_slider", "frequency_slider"]) {
  bind(id, "input", onParameterChange);
}
bind("boundary_select", "change", onParameterChange);
bind("continuum_checkbox", "change", onParameterChange);
bind("driver_checkbox", "change", onDriverChange);

readParameters();
drawAll();
window.requestAnimationFrame(animationFrame);
