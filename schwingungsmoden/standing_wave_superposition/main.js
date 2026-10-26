"use strict";

/*
 * Standing Wave Superposition
 *
 * The application evaluates prescribed 1D and 2D standing-wave modes directly.
 * There is no numerical integration of the equations of motion.
 * All 2D displacements are confined to the x-y plane.
 */

// -----------------------------------------------------------------------------
// DOM helpers and application state
// -----------------------------------------------------------------------------

const el = (id) => document.getElementById(id);
const floatValue = (id, fallback = 0) => {
  const element = el(id);
  return element ? Number.parseFloat(element.value) : fallback;
};
const intValue = (id, fallback = 0) => {
  const element = el(id);
  return element ? Math.trunc(Number(element.value)) : fallback;
};
const isChecked = (id, fallback = false) => {
  const element = el(id);
  return element ? element.checked : fallback;
};
const setText = (id, text) => {
  const element = el(id);
  if (element) element.textContent = String(text);
};
const setHtml = (id, html) => {
  const element = el(id);
  if (element) element.innerHTML = html;
};
const signedFixed = (value, digits = 2) =>
  `${value >= 0 ? "+" : ""}${value.toFixed(digits)}`;

const canvas = el("sim_canvas");
const ctx = canvas.getContext("2d");
const TWO_PI = 2 * Math.PI;

// The phase represents omega_1 * t. At phase zero all cosine factors are one.
let phase = 0;
let isRunning = false;
let lastTimestamp = null;

// The five 1D amplitude settings persist when fewer modes are displayed.
const amplitudes1D = [0, 0.65, 0, 0, 0, 0];

// The 2D mode matrix retains hidden modes when the grid size is reduced.
const MAX_2D_MODES = 5;
const activeModes2D = Array.from({ length: MAX_2D_MODES + 1 }, () =>
  Array(MAX_2D_MODES + 1).fill(false)
);
activeModes2D[1][1] = true;

// -----------------------------------------------------------------------------
// Dynamically generated controls
// -----------------------------------------------------------------------------

function readCurrent1DAmplitudes() {
  for (let n = 1; n <= 5; n += 1) {
    const slider = el(`amp_1d_${n}`);
    if (slider) amplitudes1D[n] = Number(slider.value);
  }
}

function build1DAmplitudeControls() {
  const container = el("amplitude_controls_1d");
  if (!container) return;

  container.innerHTML = "";
  const modeCount = intValue("active_modes_1d_slider", 3);

  for (let n = 1; n <= modeCount; n += 1) {
    const item = document.createElement("div");
    item.className = "amplitude-item";
    item.innerHTML = `
      <label class="slider-label" for="amp_1d_${n}">
        <span>Amplitude A<sub>${n}</sub></span>
        <output id="amp_1d_${n}_value">${signedFixed(amplitudes1D[n])}</output>
      </label>
      <input id="amp_1d_${n}" type="range" min="-1" max="1"
             step="0.05" value="${amplitudes1D[n]}" />
      <p class="microcopy">Mode ${n}: ${n} half-wavelength${n === 1 ? "" : "s"} between fixed ends.</p>
    `;
    container.appendChild(item);
    el(`amp_1d_${n}`).addEventListener("input", onInput);
  }
}

function build2DModeMatrixControls() {
  const container = el("mode_matrix_2d");
  if (!container) return;

  const modeCount = intValue("mode_count_2d_slider", 3);
  container.innerHTML = "";
  container.style.gridTemplateColumns = `repeat(${modeCount}, minmax(0, 1fr))`;

  // Rows are indexed by n; columns are indexed by m.
  for (let n = 1; n <= modeCount; n += 1) {
    for (let m = 1; m <= modeCount; m += 1) {
      const button = document.createElement("button");
      button.className = "mode-cell";
      if (activeModes2D[m][n]) button.classList.add("active");
      button.type = "button";
      button.dataset.m = String(m);
      button.dataset.n = String(n);
      button.setAttribute("aria-pressed", String(activeModes2D[m][n]));
      button.innerHTML = `
        <span class="mode-cell-title">(${m},${n})</span>
        <span class="mode-cell-sub">m=${m}, n=${n}</span>
      `;
      button.addEventListener("click", onToggle2DMode);
      container.appendChild(button);
    }
  }
}

// -----------------------------------------------------------------------------
// Labels, explanatory text and visible controls
// -----------------------------------------------------------------------------

function updateLabels() {
  setText("speed_value", `${floatValue("speed_slider", 1).toFixed(2)}×`);
  setText("phase_value", `${intValue("phase_slider", 0)}°`);
  setText("elements_1d_value", intValue("elements_1d_slider", 24));
  setText("active_modes_1d_value", intValue("active_modes_1d_slider", 3));

  const modeCount = intValue("mode_count_2d_slider", 3);
  setText("mode_count_2d_value", `${modeCount} × ${modeCount}`);
  setText("displacement_scale_2d_value",
    `${floatValue("displacement_scale_2d_slider", 1).toFixed(2)}×`);

  for (let n = 1; n <= 5; n += 1) {
    const slider = el(`amp_1d_${n}`);
    if (slider) setText(`amp_1d_${n}_value`, signedFixed(Number(slider.value)));
  }

  setText("active_modes_2d_value", countActive2DModes());
}

function updateFormulaText() {
  if (el("model_select").value === "1d") {
    setHtml("formula_text", `
      <p>For a string with fixed endpoints:</p>
      <code>y(x,t) = Σ Aₙ · sin(nπx/L) · cos(ωₙt)</code>
      <p>Only integer multiples of half a wavelength satisfy y = 0 at both ends.</p>
      <p>With physical frequency ratios enabled: ωₙ = n · ω₁.</p>
    `);
  } else {
    setHtml("formula_text", `
      <p>Interior masses of the planar lattice move within the x-y plane:</p>
      <code>x′ = x + u(x,y,t)<br>y′ = y + v(x,y,t)</code>
      <code>Mode (m,n) shape: sin(mπx/Lₓ) · sin(nπy/Lᵧ)</code>
      <p>Each cell in the mode matrix toggles one mode (m,n).</p>
      <p>The sine factors vanish at the fixed boundaries, keeping all boundary nodes stationary.</p>
    `);
  }
}

function updateVisibleControls() {
  const is1D = el("model_select").value === "1d";
  el("controls_1d").classList.toggle("hidden", !is1D);
  el("controls_2d").classList.toggle("hidden", is1D);

  setText("view_title", is1D ? "1D String with Fixed Ends" : "2D Lattice with Fixed Boundaries");
  setText("view_hint", is1D
    ? "Discrete nodes connected by straight lines."
    : "Click cells in the mode matrix to toggle individual modes.");
  updateFormulaText();
}

// -----------------------------------------------------------------------------
// Standing-wave model
// -----------------------------------------------------------------------------

function frequencyFactor1D(n) {
  // For a uniform ideal string: omega_n = n * omega_1.
  return isChecked("physical_frequency_checkbox", true) ? n : 1;
}

function frequencyFactor2D(m, n) {
  // Qualitative approximation; normalize the fundamental (1,1) to omega_1.
  return isChecked("physical_frequency_checkbox", true)
    ? Math.sqrt(m * m + n * n) / Math.sqrt(2)
    : 1;
}

function displacement1D(xNormalized, currentPhase) {
  const modeCount = intValue("active_modes_1d_slider", 3);
  let displacement = 0;
  for (let n = 1; n <= modeCount; n += 1) {
    displacement += amplitudes1D[n] * Math.sin(n * Math.PI * xNormalized)
      * Math.cos(frequencyFactor1D(n) * currentPhase);
  }
  return displacement;
}

function displacement1DSingleMode(xNormalized, currentPhase, n) {
  return amplitudes1D[n] * Math.sin(n * Math.PI * xNormalized)
    * Math.cos(frequencyFactor1D(n) * currentPhase);
}

function directionVector2D() {
  const direction = el("direction_2d_select").value;
  if (direction === "x") return [1, 0];
  if (direction === "diagonal") {
    return [1 / Math.sqrt(2), 1 / Math.sqrt(2)];
  }
  return [0, 1];
}

function displacement2D(u, v, currentPhase, singleMode = null) {
  const modeCount = intValue("mode_count_2d_slider", 3);
  const [dirX, dirY] = directionVector2D();
  let dx = 0;
  let dy = 0;

  for (let m = 1; m <= modeCount; m += 1) {
    for (let n = 1; n <= modeCount; n += 1) {
      if (singleMode === null) {
        if (!activeModes2D[m][n]) continue;
      } else if (m !== singleMode[0] || n !== singleMode[1]) {
        continue;
      }

      const shape = Math.sin(m * Math.PI * u) * Math.sin(n * Math.PI * v);
      const timePart = Math.cos(frequencyFactor2D(m, n) * currentPhase);
      const contribution = shape * timePart;
      dx += dirX * contribution;
      dy += dirY * contribution;
    }
  }
  return [dx, dy];
}

// -----------------------------------------------------------------------------
// Canvas drawing helpers
// -----------------------------------------------------------------------------

function clearCanvas() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
}

function drawWallSupport(x, y, side = "left") {
  ctx.save();
  ctx.strokeStyle = "#334155";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(x, y - 55);
  ctx.lineTo(x, y + 55);
  ctx.stroke();

  const direction = side === "left" ? -1 : 1;
  for (let k = -4; k <= 4; k += 1) {
    const yy = y + k * 12;
    ctx.beginPath();
    ctx.moveTo(x, yy);
    ctx.lineTo(x + direction * 14, yy + 8);
    ctx.stroke();
  }
  ctx.restore();
}

function drawPolyline(points, color = "#1d4ed8", lineWidth = 2, alpha = 1) {
  if (points.length < 2) return;
  ctx.save();
  ctx.globalAlpha = alpha;
  ctx.strokeStyle = color;
  ctx.lineWidth = lineWidth;
  ctx.beginPath();
  ctx.moveTo(points[0][0], points[0][1]);
  for (let i = 1; i < points.length; i += 1) {
    ctx.lineTo(points[i][0], points[i][1]);
  }
  ctx.stroke();
  ctx.restore();
}

function drawPoints(points, radius = 4, color = "#1d4ed8", alpha = 1) {
  ctx.save();
  ctx.globalAlpha = alpha;
  ctx.fillStyle = color;
  for (const [x, y] of points) {
    ctx.beginPath();
    ctx.arc(x, y, radius, 0, TWO_PI);
    ctx.fill();
  }
  ctx.restore();
}

// -----------------------------------------------------------------------------
// 1D string visualization
// -----------------------------------------------------------------------------

function draw1D() {
  clearCanvas();
  const left = 100;
  const right = canvas.width - 100;
  const length = right - left;
  const middleY = canvas.height / 2;
  const yScale = 110;

  const elements = intValue("elements_1d_slider", 24);
  const modeCount = intValue("active_modes_1d_slider", 3);
  const showModes = isChecked("show_modes_checkbox", true);

  // Undisplaced string (reference line).
  ctx.save();
  ctx.strokeStyle = "#cbd5e1";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(left, middleY);
  ctx.lineTo(right, middleY);
  ctx.stroke();
  ctx.restore();

  // Display active individual contributions in the background.
  if (showModes) {
    for (let n = 1; n <= modeCount; n += 1) {
      if (Math.abs(amplitudes1D[n]) < 0.001) continue;
      const modePoints = [];
      for (let i = 0; i <= elements; i += 1) {
        const u = i / elements;
        modePoints.push([
          left + u * length,
          middleY - yScale * displacement1DSingleMode(u, phase, n)
        ]);
      }
      drawPolyline(modePoints, "#64748b", 1.5, 0.28);
    }
  }

  // Superposed displacement.
  const points = [];
  for (let i = 0; i <= elements; i += 1) {
    const u = i / elements;
    points.push([left + u * length, middleY - yScale * displacement1D(u, phase)]);
  }
  drawPolyline(points, "#1d4ed8", 3, 1);
  drawPoints(points, 4, "#1d4ed8", 1);

  drawPoints([points[0], points[points.length - 1]], 6, "#c2410c", 1);
  drawWallSupport(left - 8, middleY, "left");
  drawWallSupport(right + 8, middleY, "right");

  ctx.save();
  ctx.fillStyle = "#475569";
  ctx.font = "18px system-ui";
  ctx.fillText("Fixed ends: y = 0", left, middleY + 90);
  ctx.fillText(`${elements} elements, ${elements + 1} nodes`, left, middleY + 118);
  ctx.restore();
}

// -----------------------------------------------------------------------------
// 2D in-plane lattice visualization
// -----------------------------------------------------------------------------

function gridPoints2D(singleMode = null, restPosition = false) {
  const inner = intValue("mode_count_2d_slider", 3);
  const total = inner + 2;
  const gridWidth = Math.min(canvas.width * 0.68, canvas.height * 0.72);
  const gridHeight = gridWidth;
  const left = (canvas.width - gridWidth) / 2;
  const top = (canvas.height - gridHeight) / 2;

  // Normalize visible displacement to avoid extreme distortion with many modes.
  const visualScale = floatValue("displacement_scale_2d_slider", 1);
  const activeCount = Math.max(1, countActive2DModes());
  const displacementScale = gridWidth * 0.11 * visualScale / Math.sqrt(activeCount);

  const points = [];
  for (let j = 0; j < total; j += 1) {
    const row = [];
    const v = j / (total - 1);
    for (let i = 0; i < total; i += 1) {
      const u = i / (total - 1);
      const baseX = left + u * gridWidth;
      const baseY = top + v * gridHeight;
      const isBorder = i === 0 || i === total - 1 || j === 0 || j === total - 1;
      const [dx, dy] = restPosition || isBorder
        ? [0, 0] : displacement2D(u, v, phase, singleMode);
      row.push([baseX + dx * displacementScale, baseY + dy * displacementScale]);
    }
    points.push(row);
  }
  return points;
}

function drawWireGrid(points, color = "#1d4ed8", lineWidth = 2, alpha = 1) {
  const ny = points.length;
  const nx = points[0].length;
  ctx.save();
  ctx.globalAlpha = alpha;
  ctx.strokeStyle = color;
  ctx.lineWidth = lineWidth;

  for (let j = 0; j < ny; j += 1) {
    ctx.beginPath();
    ctx.moveTo(points[j][0][0], points[j][0][1]);
    for (let i = 1; i < nx; i += 1) ctx.lineTo(points[j][i][0], points[j][i][1]);
    ctx.stroke();
  }
  for (let i = 0; i < nx; i += 1) {
    ctx.beginPath();
    ctx.moveTo(points[0][i][0], points[0][i][1]);
    for (let j = 1; j < ny; j += 1) ctx.lineTo(points[j][i][0], points[j][i][1]);
    ctx.stroke();
  }
  ctx.restore();
}

function countActive2DModes() {
  const modeCount = intValue("mode_count_2d_slider", 3);
  let count = 0;
  for (let m = 1; m <= modeCount; m += 1) {
    for (let n = 1; n <= modeCount; n += 1) {
      if (activeModes2D[m][n]) count += 1;
    }
  }
  return count;
}

function active2DModeText() {
  const modeCount = intValue("mode_count_2d_slider", 3);
  const active = [];
  for (let n = 1; n <= modeCount; n += 1) {
    for (let m = 1; m <= modeCount; m += 1) {
      if (activeModes2D[m][n]) active.push(`(${m},${n})`);
    }
  }
  return active.length ? active.join(", ") : "none";
}

function draw2D() {
  clearCanvas();
  const modeCount = intValue("mode_count_2d_slider", 3);
  const showModes = isChecked("show_modes_checkbox", true);

  const restPoints = gridPoints2D(null, true);
  drawWireGrid(restPoints, "#cbd5e1", 1, 0.55);

  if (showModes) {
    for (let m = 1; m <= modeCount; m += 1) {
      for (let n = 1; n <= modeCount; n += 1) {
        if (!activeModes2D[m][n]) continue;
        drawWireGrid(gridPoints2D([m, n]), "#64748b", 1, 0.14);
      }
    }
  }

  const points = gridPoints2D();
  drawWireGrid(points, "#1d4ed8", 2.2, 1);

  const total = modeCount + 2;
  const borderPoints = [];
  const interiorPoints = [];
  for (let j = 0; j < total; j += 1) {
    for (let i = 0; i < total; i += 1) {
      const isBorder = i === 0 || i === total - 1 || j === 0 || j === total - 1;
      (isBorder ? borderPoints : interiorPoints).push(points[j][i]);
    }
  }
  drawPoints(interiorPoints, 4.2, "#1d4ed8", 1);
  drawPoints(borderPoints, 4.2, "#c2410c", 1);

  ctx.save();
  ctx.fillStyle = "#475569";
  ctx.font = "18px system-ui";
  ctx.fillText("Fixed boundaries: boundary nodes remain stationary", 34, 42);
  ctx.fillText(`${modeCount} × ${modeCount} interior masses, active modes: ${active2DModeText()}`, 34, 70);
  ctx.fillText("In-plane only (no z-axis)", 34, 98);
  ctx.restore();
}

function draw() {
  if (el("model_select").value === "1d") draw1D();
  else draw2D();
}

// -----------------------------------------------------------------------------
// Interaction
// -----------------------------------------------------------------------------

function onInput() {
  readCurrent1DAmplitudes();
  phase = (floatValue("phase_slider", 0) / 360) * TWO_PI;
  updateLabels();
  draw();
}

function onRebuild1D() {
  readCurrent1DAmplitudes();
  build1DAmplitudeControls();
  updateLabels();
  draw();
}

function onRebuild2D() {
  build2DModeMatrixControls();
  updateLabels();
  draw();
}

function onToggle2DMode(event) {
  const m = Number(event.currentTarget.dataset.m);
  const n = Number(event.currentTarget.dataset.n);
  activeModes2D[m][n] = !activeModes2D[m][n];
  build2DModeMatrixControls();
  updateLabels();
  draw();
}

function onModelChange() {
  readCurrent1DAmplitudes();
  updateVisibleControls();
  updateLabels();
  draw();
}

function onPlayPause() {
  isRunning = !isRunning;
  lastTimestamp = null;
  setText("play_button", isRunning ? "⏸ Pause" : "▶ Play");
  setText("status_text", isRunning ? "Running" : "Paused");
}

function onReset() {
  // As in the original, Reset affects the phase only, not mode selections.
  phase = 0;
  lastTimestamp = null;
  el("phase_slider").value = "0";
  updateLabels();
  draw();
}

// -----------------------------------------------------------------------------
// Animation
// -----------------------------------------------------------------------------

function animate(timestamp) {
  if (isRunning) {
    if (lastTimestamp === null) lastTimestamp = timestamp;
    const dt = (timestamp - lastTimestamp) / 1000;
    lastTimestamp = timestamp;

    const speed = floatValue("speed_slider", 1);
    const omegaBase = 1.4; // Visualization rate, not a calibrated SI frequency.
    phase += omegaBase * speed * dt;

    const phaseDegrees = ((phase % TWO_PI) / TWO_PI) * 360;
    el("phase_slider").value = String(phaseDegrees);
    updateLabels();
    draw();
  }
  window.requestAnimationFrame(animate);
}

// -----------------------------------------------------------------------------
// Initialization
// -----------------------------------------------------------------------------

el("model_select").addEventListener("change", onModelChange);
el("play_button").addEventListener("click", onPlayPause);
el("reset_button").addEventListener("click", onReset);

for (const id of [
  "speed_slider", "phase_slider", "elements_1d_slider",
  "displacement_scale_2d_slider", "physical_frequency_checkbox",
  "show_modes_checkbox"
]) {
  el(id).addEventListener("input", onInput);
}
el("direction_2d_select").addEventListener("change", onInput);
el("active_modes_1d_slider").addEventListener("input", onRebuild1D);
el("mode_count_2d_slider").addEventListener("input", onRebuild2D);

build1DAmplitudeControls();
build2DModeMatrixControls();
updateVisibleControls();
updateLabels();
setText("status_text", "Paused");
draw();
window.requestAnimationFrame(animate);
