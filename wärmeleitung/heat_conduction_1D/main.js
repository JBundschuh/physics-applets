"use strict";

/*
 * Temperature-Field Heat Conduction — simplified Fourier model
 *
 * Each column has one temperature value. Heat conduction is computed in one
 * dimension through pairwise exchange between neighboring columns. The 2D grid
 * is a visualization only: warmer nodes move more strongly and appear redder.
 * Node motion does not affect the temperature calculation.
 */

// ---------------------------------------------------------------------------
// DOM helpers and canvas contexts
// ---------------------------------------------------------------------------

function element(id) {
  return document.getElementById(id);
}

function sliderValue(id, fallback = 0) {
  const control = element(id);
  return control ? Number(control.value) : fallback;
}

function isChecked(id) {
  return element(id).checked;
}

function setText(id, text) {
  element(id).textContent = String(text);
}

const simulationCanvas = element("sim_canvas");
const simulationContext = simulationCanvas.getContext("2d");
const profileCanvas = element("profile_canvas");
const profileContext = profileCanvas.getContext("2d");

// ---------------------------------------------------------------------------
// Model parameters and state
// ---------------------------------------------------------------------------

const COLUMNS = 10;
const ROWS = 10;
const NODE_COUNT = COLUMNS * ROWS;

// This factor controls only the visible node motion, not heat conduction.
const JITTER_STRENGTH = 1.0;

let temperatures = [];
let initialTemperatureSum = 0;
let phaseX = [];
let phaseY = [];
let frequencyX = [];
let frequencyY = [];
let isRunning = false;
let frameCounter = 0;
let simulationTime = 0;

// ---------------------------------------------------------------------------
// Mathematical and visual helpers
// ---------------------------------------------------------------------------

function clamp(value, low, high) {
  return Math.max(low, Math.min(high, value));
}

function lerp(start, end, fraction) {
  return start + (end - start) * fraction;
}

function nodeIndex(column, row) {
  return row * COLUMNS + column;
}

function temperatureColor(temperature) {
  // Blue = cool, near-white = intermediate, orange/red = warm.
  const t = clamp(temperature / 120, 0, 1);
  const cold = [45, 100, 220];
  const middle = [240, 246, 255];
  const hot = [230, 80, 25];
  const start = t < 0.5 ? cold : middle;
  const end = t < 0.5 ? middle : hot;
  const fraction = t < 0.5 ? t / 0.5 : (t - 0.5) / 0.5;

  // Math.trunc matches the integer conversion in the original Python code.
  const rgb = start.map((component, index) =>
    Math.trunc(lerp(component, end[index], fraction))
  );
  return `rgb(${rgb[0]},${rgb[1]},${rgb[2]})`;
}

function temperatureToJitterAmplitude(temperature) {
  // The square root keeps the visual displacement moderate at high values.
  return JITTER_STRENGTH * 7.5 * Math.sqrt(Math.max(0, temperature) / 120);
}

function sumTemperatures() {
  return temperatures.reduce((sum, temperature) => sum + temperature, 0);
}

// ---------------------------------------------------------------------------
// Initialization and heat conduction
// ---------------------------------------------------------------------------

function initialTemperatureForColumn(column) {
  if (column === 0) return sliderValue("temp_left_slider", 100);
  if (column === COLUMNS - 1) return sliderValue("temp_right_slider", 20);
  return sliderValue("temp_middle_slider", 20);
}

function initializeModel() {
  // Read the currently selected initial temperatures for all columns.
  temperatures = Array.from({ length: COLUMNS }, (_, column) =>
    initialTemperatureForColumn(column)
  );
  initialTemperatureSum = sumTemperatures();

  // Random phases and frequencies are used for visualization only.
  phaseX = [];
  phaseY = [];
  frequencyX = [];
  frequencyY = [];

  for (let node = 0; node < NODE_COUNT; node++) {
    phaseX.push(2 * Math.PI * Math.random());
    phaseY.push(2 * Math.PI * Math.random());
    frequencyX.push(1.2 + 2.8 * Math.random());
    frequencyY.push(1.2 + 2.8 * Math.random());
  }

  simulationTime = 0;
  frameCounter = 0;
  updateLabelsAndStatistics();
  drawAll();
}

function heatExchangeStep() {
  // Exchange between adjacent columns, based on the same previous state.
  // Without fixed boundary temperatures, the sum is conserved apart from
  // floating-point rounding.
  const exchangeFactor = sliderValue("diffusion_slider", 0.18);
  const changes = new Array(COLUMNS).fill(0);

  for (let column = 0; column < COLUMNS - 1; column++) {
    const difference = temperatures[column] - temperatures[column + 1];
    const transfer = exchangeFactor * difference;
    changes[column] -= transfer;
    changes[column + 1] += transfer;
  }

  for (let column = 0; column < COLUMNS; column++) {
    temperatures[column] += changes[column];
  }

  // Optional fixed-temperature reservoirs affect only the outer columns.
  if (isChecked("thermostat_checkbox")) {
    temperatures[0] = sliderValue("temp_left_slider", 100);
    temperatures[COLUMNS - 1] = sliderValue("temp_right_slider", 20);
  }
}

function advanceSimulation() {
  // Preserve the original relationship between the speed slider and updates.
  const speed = sliderValue("speed_slider", 1);
  const substeps = Math.max(1, Math.round(2 * speed));

  for (let step = 0; step < substeps; step++) {
    heatExchangeStep();
    simulationTime += 0.035;
  }
}

// ---------------------------------------------------------------------------
// Grid rendering
// ---------------------------------------------------------------------------

function gridGeometry() {
  const margin = 74;
  return {
    left: margin,
    top: margin,
    stepX: (simulationCanvas.width - 2 * margin) / (COLUMNS - 1),
    stepY: (simulationCanvas.height - 2 * margin) / (ROWS - 1),
  };
}

function restPosition(column, row) {
  const { left, top, stepX, stepY } = gridGeometry();
  return [left + column * stepX, top + row * stepY];
}

function nodePosition(column, row) {
  const [x, y] = restPosition(column, row);
  const node = nodeIndex(column, row);
  const amplitude = temperatureToJitterAmplitude(temperatures[column]);

  // Visual oscillation around each node's fixed position.
  const dx = amplitude * Math.sin(phaseX[node] + frequencyX[node] * simulationTime);
  const dy = amplitude * Math.cos(phaseY[node] + frequencyY[node] * simulationTime);
  return [x + dx, y + dy];
}

function clearCanvas(context, canvas) {
  context.clearRect(0, 0, canvas.width, canvas.height);
}

function drawGridPaths() {
  // These lines show the grid structure; they are not mechanical springs.
  simulationContext.save();
  simulationContext.strokeStyle = "rgba(60, 75, 100, 0.30)";
  simulationContext.lineWidth = 1.25;
  simulationContext.beginPath();

  for (let row = 0; row < ROWS; row++) {
    for (let column = 0; column < COLUMNS - 1; column++) {
      const [x1, y1] = nodePosition(column, row);
      const [x2, y2] = nodePosition(column + 1, row);
      simulationContext.moveTo(x1, y1);
      simulationContext.lineTo(x2, y2);
    }
  }

  for (let column = 0; column < COLUMNS; column++) {
    for (let row = 0; row < ROWS - 1; row++) {
      const [x1, y1] = nodePosition(column, row);
      const [x2, y2] = nodePosition(column, row + 1);
      simulationContext.moveTo(x1, y1);
      simulationContext.lineTo(x2, y2);
    }
  }

  simulationContext.stroke();
  simulationContext.restore();
}

function drawNodes() {
  for (let row = 0; row < ROWS; row++) {
    for (let column = 0; column < COLUMNS; column++) {
      const [x, y] = nodePosition(column, row);
      const outerColumn = column === 0 || column === COLUMNS - 1;

      simulationContext.beginPath();
      simulationContext.arc(x, y, 7.5, 0, 2 * Math.PI);
      simulationContext.fillStyle = temperatureColor(temperatures[column]);
      simulationContext.fill();
      simulationContext.lineWidth = outerColumn ? 2.2 : 1.1;
      simulationContext.strokeStyle = outerColumn
        ? "rgba(30, 40, 70, 0.75)"
        : "rgba(30, 40, 70, 0.42)";
      simulationContext.stroke();
    }
  }
}

function drawSimulationHint() {
  simulationContext.save();
  simulationContext.font = "14px system-ui, sans-serif";
  if (isChecked("thermostat_checkbox")) {
    simulationContext.fillStyle = "rgba(194, 65, 12, 0.95)";
    simulationContext.fillText("Fixed boundary temperatures", 26, 38);
  } else {
    simulationContext.fillStyle = "rgba(47, 109, 246, 0.95)";
    simulationContext.fillText("Closed system", 26, 38);
  }
  simulationContext.restore();
}

function drawSimulation() {
  clearCanvas(simulationContext, simulationCanvas);
  simulationContext.save();
  simulationContext.fillStyle = "rgba(247, 249, 252, 0.85)";
  simulationContext.fillRect(0, 0, simulationCanvas.width, simulationCanvas.height);
  simulationContext.restore();

  // The grid and visual thermal motion are always enabled.
  drawGridPaths();
  drawNodes();
  drawSimulationHint();
}

// ---------------------------------------------------------------------------
// Temperature profile
// ---------------------------------------------------------------------------

function drawProfile() {
  clearCanvas(profileContext, profileCanvas);

  const width = profileCanvas.width;
  const height = profileCanvas.height;
  const marginLeft = 54;
  const marginRight = 26;
  const marginTop = 24;
  const marginBottom = 42;
  const plotWidth = width - marginLeft - marginRight;
  const plotHeight = height - marginTop - marginBottom;
  const maxTemperature = Math.max(120, Math.max(...temperatures) * 1.15);

  profileContext.save();
  profileContext.strokeStyle = "rgba(120, 135, 160, 0.25)";
  profileContext.lineWidth = 1;
  profileContext.beginPath();
  for (const fraction of [0, 0.25, 0.5, 0.75, 1]) {
    const gridY = marginTop + plotHeight * (1 - fraction);
    profileContext.moveTo(marginLeft, gridY);
    profileContext.lineTo(marginLeft + plotWidth, gridY);
  }
  profileContext.stroke();

  // Axes.
  profileContext.strokeStyle = "rgba(30, 40, 70, 0.55)";
  profileContext.beginPath();
  profileContext.moveTo(marginLeft, marginTop);
  profileContext.lineTo(marginLeft, marginTop + plotHeight);
  profileContext.lineTo(marginLeft + plotWidth, marginTop + plotHeight);
  profileContext.stroke();

  const points = temperatures.map((temperature, column) => ({
    x: marginLeft + (plotWidth * column) / (COLUMNS - 1),
    y: marginTop + plotHeight * (1 - clamp(temperature / maxTemperature, 0, 1)),
    temperature,
  }));

  profileContext.strokeStyle = "#2f6df6";
  profileContext.lineWidth = 2.4;
  profileContext.beginPath();
  points.forEach((point, index) => {
    if (index === 0) profileContext.moveTo(point.x, point.y);
    else profileContext.lineTo(point.x, point.y);
  });
  profileContext.stroke();

  for (const { x, y, temperature } of points) {
    profileContext.beginPath();
    profileContext.arc(x, y, 5.5, 0, 2 * Math.PI);
    profileContext.fillStyle = temperatureColor(temperature);
    profileContext.fill();
    profileContext.strokeStyle = "rgba(30, 40, 70, 0.55)";
    profileContext.lineWidth = 1;
    profileContext.stroke();
  }

  profileContext.fillStyle = "#657086";
  profileContext.font = "13px system-ui, sans-serif";
  profileContext.fillText("Column", marginLeft + plotWidth / 2 - 22, height - 12);
  profileContext.fillText("T", 20, marginTop + 5);
  profileContext.fillText("1", marginLeft - 3, height - 18);
  profileContext.fillText(String(COLUMNS), marginLeft + plotWidth - 8, height - 18);
  profileContext.restore();
}

function drawAll() {
  drawSimulation();
  drawProfile();
}

// ---------------------------------------------------------------------------
// Controls and statistics
// ---------------------------------------------------------------------------

function updateLabelsAndStatistics() {
  setText("speed_value", `${sliderValue("speed_slider", 1).toFixed(2)}×`);
  setText("diffusion_value", sliderValue("diffusion_slider", 0.18).toFixed(2));
  setText("temp_left_value", sliderValue("temp_left_slider", 100).toFixed(0));
  setText("temp_middle_value", sliderValue("temp_middle_slider", 20).toFixed(0));
  setText("temp_right_value", sliderValue("temp_right_slider", 20).toFixed(0));
  setText("play_button", isRunning ? "⏸ Pause" : "▶ Start");

  const total = sumTemperatures();
  const mean = total / COLUMNS;
  const difference = Math.max(...temperatures) - Math.min(...temperatures);
  setText("mean_temp_value", mean.toFixed(1));
  setText("delta_temp_value", difference.toFixed(1));
  setText("total_temp_value", total.toFixed(1));

  if (Math.abs(initialTemperatureSum) > 1e-12) {
    const drift = (100 * (total - initialTemperatureSum)) / initialTemperatureSum;
    // Avoid displaying negative zero for floating-point rounding errors.
    const displayedDrift = Math.abs(drift) < 0.005 ? 0 : drift;
    setText("total_drift_value", `${displayedDrift >= 0 ? "+" : ""}${displayedDrift.toFixed(2)} %`);
  } else {
    setText("total_drift_value", "–");
  }
}

function togglePlay() {
  isRunning = !isRunning;
  updateLabelsAndStatistics();
}

function resetSimulation() {
  isRunning = false;
  initializeModel();
}

function onModelInput() {
  updateLabelsAndStatistics();
  drawAll();
}

function onTemperatureInput() {
  // Changing initial temperatures while paused resets the field. While
  // running, only the boundary sliders can act through fixed reservoirs.
  if (!isRunning) initializeModel();
  else updateLabelsAndStatistics();
}

function animationLoop() {
  if (isRunning) {
    advanceSimulation();
    frameCounter++;
    if (frameCounter % 4 === 0) updateLabelsAndStatistics();
    drawAll();
  }
  window.requestAnimationFrame(animationLoop);
}

// ---------------------------------------------------------------------------
// Event listeners and startup
// ---------------------------------------------------------------------------

element("play_button").addEventListener("click", togglePlay);
element("reset_button").addEventListener("click", resetSimulation);

for (const id of ["speed_slider", "diffusion_slider"]) {
  element(id).addEventListener("input", onModelInput);
}
for (const id of ["temp_left_slider", "temp_middle_slider", "temp_right_slider"]) {
  element(id).addEventListener("input", onTemperatureInput);
}
element("thermostat_checkbox").addEventListener("change", onModelInput);

initializeModel();
window.requestAnimationFrame(animationLoop);
