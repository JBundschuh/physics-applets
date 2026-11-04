/*
 * Phasor Formalism – Fundamentals
 *
 * Standalone browser implementation of the former PyScript applet.
 * Vector mode: arrows with movable start and end points, including snapping.
 * Phasor mode: arrows anchored at the origin of the complex plane.
 * The model calculates vector components, complex sums, phase, and magnitude squared.
 * Wavelength and path-difference controls affect an independent example phasor.
 * No external libraries or Python runtime are needed.
 */

(() => {
  "use strict";

  const byId = (id) => document.getElementById(id);
  const canvas = byId("phasor-canvas");
  const ctx = canvas.getContext("2d");
  if (!ctx) {
    throw new Error("This browser does not support the 2D canvas context.");
  }

  const ui = {
    mode: byId("mode-select"),
    preset: byId("preset-select"),
    showResult: byId("result-toggle"),
    showPhase: byId("phase-toggle"),
    showSquare: byId("square-toggle"),
    showIndividual: byId("individual-toggle"),
    showAxes: byId("axis-label-toggle"),
    showEquations: byId("formula-toggle"),
    undo: byId("undo-button"),
    deleteSelected: byId("delete-button"),
    clearAll: byId("reset-button"),
    phasorControls: byId("phasor-controls"),
    wavelength: byId("wavelength-slider"),
    pathDifference: byId("path-slider"),
    wavelengthReadout: byId("wavelength-readout"),
    pathReadout: byId("path-readout"),
    colorPreview: byId("color-preview"),
    colorName: byId("color-name"),
    formulaPanel: byId("formula-panel"),
    sumHeading: byId("sum-heading"),
    sumFormula: byId("sum-formula"),
    magnitudeFormula: byId("magnitude-formula"),
    pathPhaseFormula: byId("path-phase-formula"),
    formulaWavelength: byId("formula-lambda"),
    formulaPath: byId("formula-path"),
    formulaPhase: byId("formula-phase"),
    countReadout: byId("count-readout"),
    resultReadout: byId("result-readout"),
    phaseReadout: byId("phase-readout"),
    squareReadout: byId("square-readout"),
    badge: byId("mode-badge"),
    hint: byId("interaction-hint"),
  };

  const WIDTH = canvas.width;
  const HEIGHT = canvas.height;
  const CX = WIDTH / 2;
  const CY = HEIGHT / 2;
  const UNIT = 60;
  const MIN_LENGTH = 8;
  const SNAP_DISTANCE = 22;
  const HANDLE_RADIUS = 8;
  const HIT_DISTANCE = 9;
  const TAU = Math.PI * 2;
  const BLUE = "#4257ff";
  const DARK = "#111827";

  let vectors = [];
  let selectedIndex = null;
  let previewVector = null;
  let dragMode = null; // "new", "start", "end", "move"
  let dragStartPos = null;
  let dragOriginal = null;
  let activePointerId = null;

  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
  const distance = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
  const fmt = (value, digits = 2) => {
    const normalized = Math.abs(value) < 0.5 * 10 ** (-digits) ? 0 : value;
    return normalized.toFixed(digits);
  };
  const currentMode = () => ui.mode.value;
  const isPhasorMode = () => currentMode() === "phasor";
  const origin = () => ({ x: CX, y: CY });
  const wavelength = () => Number(ui.wavelength.value);
  const pathDifference = () => Number(ui.pathDifference.value);

  function canvasPoint(event) {
    const rect = canvas.getBoundingClientRect();
    return {
      x: (event.clientX - rect.left) * WIDTH / rect.width,
      y: (event.clientY - rect.top) * HEIGHT / rect.height,
    };
  }

  function vectorComponents(vector) {
    return {
      x: vector.ex - vector.sx,
      y: vector.ey - vector.sy,
    };
  }

  function complexComponents(vector) {
    const d = vectorComponents(vector);
    return { re: d.x / UNIT, im: -d.y / UNIT };
  }

  function complexResultant() {
    let re = 0;
    let im = 0;
    for (const vector of vectors) {
      const component = complexComponents(vector);
      re += component.re;
      im += component.im;
    }
    return { re, im };
  }

  function resultantPixels() {
    let x = 0;
    let y = 0;
    for (const vector of vectors) {
      x += vector.ex - vector.sx;
      y += vector.ey - vector.sy;
    }
    return { x, y };
  }

  function phaseDegrees(re, im) {
    return Math.abs(re) < 1e-12 && Math.abs(im) < 1e-12
      ? null
      : Math.atan2(im, re) * 180 / Math.PI;
  }

  function complexString(re, im) {
    return `${fmt(re)} ${im >= 0 ? "+" : "−"} ${fmt(Math.abs(im))} i`;
  }

  // The display colors approximate the visible spectrum, not measured sRGB values.
  function interpolateRGB(a, b, t) {
    return a.map((value, i) => Math.round(value + (b[i] - value) * t));
  }

  function wavelengthToColor(nm) {
    const w = clamp(nm, 380, 740);
    const anchors = [
      [380, [126, 72, 255], "violet"],
      [440, [35, 88, 255], "blue"],
      [485, [0, 188, 220], "cyan"],
      [510, [40, 190, 86], "green"],
      [565, [246, 218, 62], "yellow"],
      [590, [240, 132, 37], "orange"],
      [625, [225, 46, 45], "red"],
      [740, [150, 25, 35], "red"],
    ];
    for (let i = 0; i < anchors.length - 1; i += 1) {
      const [start, startRGB] = anchors[i];
      const [end, endRGB] = anchors[i + 1];
      if (w < end || i === anchors.length - 2) {
        const rgb = interpolateRGB(startRGB, endRGB, (w - start) / (end - start));
        // Match the source applet's color names for each spectral interval.
        const names = ["violet", "blue", "cyan", "green", "yellow", "orange", "red"];
        return { rgb: `rgb(${rgb.join(", ")})`, name: names[i] };
      }
    }
    return { rgb: "rgb(150, 25, 35)", name: "red" };
  }

  const currentColor = () => wavelengthToColor(wavelength()).rgb;

  function drawLine(x1, y1, x2, y2, color = "#1f2937", width = 2.5, dash = null, alpha = 1) {
    ctx.save();
    ctx.globalAlpha = alpha;
    ctx.strokeStyle = color;
    ctx.lineWidth = width;
    ctx.lineCap = "round";
    ctx.setLineDash(dash ?? []);
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.stroke();
    ctx.restore();
  }

  function drawArrow(x1, y1, x2, y2, {
    color = BLUE, width = 3, alpha = 1, label = null, dashed = false,
  } = {}) {
    const dx = x2 - x1;
    const dy = y2 - y1;
    const length = Math.hypot(dx, dy);
    if (length < 1e-6) return;

    const angle = Math.atan2(dy, dx);
    const headLength = Math.min(16, Math.max(9, length * 0.18));
    const headAngle = 26 * Math.PI / 180;

    ctx.save();
    ctx.globalAlpha = alpha;
    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    ctx.lineWidth = width;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.setLineDash(dashed ? [8, 7] : []);
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.stroke();

    ctx.beginPath();
    ctx.moveTo(x2, y2);
    ctx.lineTo(x2 - headLength * Math.cos(angle - headAngle), y2 - headLength * Math.sin(angle - headAngle));
    ctx.lineTo(x2 - headLength * Math.cos(angle + headAngle), y2 - headLength * Math.sin(angle + headAngle));
    ctx.closePath();
    ctx.fill();

    if (label) {
      ctx.font = "700 14px Inter, system-ui, sans-serif";
      ctx.fillText(label, x2 + 9, y2 - 9);
    }
    ctx.restore();
  }

  function drawHandle(x, y) {
    ctx.save();
    ctx.fillStyle = "#ffffff";
    ctx.strokeStyle = "#0f172a";
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    ctx.arc(x, y, HANDLE_RADIUS, 0, TAU);
    ctx.fill();
    ctx.stroke();
    ctx.restore();
  }

  function drawGridAndAxes() {
    ctx.clearRect(0, 0, WIDTH, HEIGHT);
    ctx.save();
    ctx.strokeStyle = "#edf2f8";
    ctx.lineWidth = 1;
    for (let x = CX % UNIT; x <= WIDTH; x += UNIT) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, HEIGHT);
      ctx.stroke();
    }
    for (let y = CY % UNIT; y <= HEIGHT; y += UNIT) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(WIDTH, y);
      ctx.stroke();
    }
    ctx.restore();

    drawLine(0, CY, WIDTH, CY, "#d2dae8", 1.7);
    drawLine(CX, 0, CX, HEIGHT, "#d2dae8", 1.7);

    ctx.save();
    ctx.fillStyle = "#9aa8bd";
    ctx.beginPath();
    ctx.arc(CX, CY, 3.5, 0, TAU);
    ctx.fill();
    ctx.restore();

    if (ui.showAxes.checked) {
      ctx.save();
      ctx.fillStyle = "#657286";
      ctx.font = "700 14px Inter, system-ui, sans-serif";
      ctx.fillText(isPhasorMode() ? "Real axis" : "x-axis", WIDTH - 90, CY - 12);
      ctx.fillText(isPhasorMode() ? "Imaginary axis" : "y-axis", CX + 12, 22);
      ctx.fillText("0", CX + 8, CY + 18);
      ctx.restore();
    }
  }

  function drawResultantPhaseArc(sx, sy, ex, ey) {
    if (!ui.showPhase.checked) return;
    const dx = ex - sx;
    const dy = ey - sy;
    if (Math.hypot(dx, dy) < 12) return;

    const angle = -Math.atan2(-dy, dx);
    const radius = 52;
    ctx.save();
    ctx.strokeStyle = "#f59e0b";
    ctx.fillStyle = "#b45309";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(sx, sy, radius, 0, angle, angle < 0);
    ctx.stroke();
    ctx.font = "700 13px Inter, system-ui, sans-serif";
    ctx.fillText("φ", sx + radius + 8, sy - 8);
    ctx.restore();
  }

  function drawVector(vector, index) {
    let label = null;
    if (ui.showIndividual.checked) {
      const { re, im } = complexComponents(vector);
      const length = Math.hypot(re, im);
      label = `${isPhasorMode() ? "z" : "v"}${index + 1}: ${fmt(length)}`;
    }
    drawArrow(vector.sx, vector.sy, vector.ex, vector.ey, {
      color: vector.color,
      width: selectedIndex === index ? 3.2 : 2.6,
      label,
    });
    if (selectedIndex === index) {
      drawHandle(vector.sx, vector.sy);
      drawHandle(vector.ex, vector.ey);
    }
  }

  function drawPhasorAdditionChain() {
    if (!isPhasorMode() || vectors.length < 2) return;
    let x = CX;
    let y = CY;
    for (const vector of vectors) {
      const { x: dx, y: dy } = vectorComponents(vector);
      const nx = x + dx;
      const ny = y + dy;
      drawArrow(x, y, nx, ny, {
        color: vector.color, width: 2, alpha: 0.32, dashed: true,
      });
      x = nx;
      y = ny;
    }
  }

  // Draw a square using the resultant as one of its sides.
  // The area is a visual analogy for |R|² or |z_total|².
  function drawSquareOnResultant(sx, sy, ex, ey) {
    const dx = ex - sx;
    const dy = ey - sy;
    const length = Math.hypot(dx, dy);
    if (length < 10) return;

    function overflowScore(nx, ny) {
      const corners = [
        [sx, sy], [ex, ey], [ex + nx, ey + ny], [sx + nx, sy + ny],
      ];
      let score = 0;
      for (const [x, y] of corners) {
        if (x < 0) score += -x;
        if (x > WIDTH) score += x - WIDTH;
        if (y < 0) score += -y;
        if (y > HEIGHT) score += y - HEIGHT;
      }
      return score;
    }

    const a = { x: -dy, y: dx };
    const b = { x: dy, y: -dx };
    const normal = overflowScore(b.x, b.y) < overflowScore(a.x, a.y) ? b : a;
    const nx = normal.x;
    const ny = normal.y;

    ctx.save();
    ctx.fillStyle = "rgba(17, 24, 39, 0.075)";
    ctx.strokeStyle = "rgba(17, 24, 39, 0.32)";
    ctx.lineWidth = 1.8;
    ctx.setLineDash([7, 6]);
    ctx.beginPath();
    ctx.moveTo(sx, sy);
    ctx.lineTo(ex, ey);
    ctx.lineTo(ex + nx, ey + ny);
    ctx.lineTo(sx + nx, sy + ny);
    ctx.closePath();
    ctx.fill();
    ctx.stroke();

    const ux = dx / length;
    const uy = dy / length;
    const vx = nx / length;
    const vy = ny / length;
    const marker = Math.min(22, length * 0.18);
    ctx.setLineDash([]);
    ctx.strokeStyle = "rgba(17, 24, 39, 0.55)";
    ctx.beginPath();
    ctx.moveTo(sx + ux * marker, sy + uy * marker);
    ctx.lineTo(sx + ux * marker + vx * marker, sy + uy * marker + vy * marker);
    ctx.lineTo(sx + vx * marker, sy + vy * marker);
    ctx.stroke();
    ctx.fillStyle = DARK;
    ctx.font = "700 14px Inter, system-ui, sans-serif";
    ctx.fillText(isPhasorMode() ? "|z|²" : "|R|²",
      sx + nx * 0.5 + dx * 0.5 - 18, sy + ny * 0.5 + dy * 0.5);
    ctx.restore();
  }

  function drawResultant() {
    if (!vectors.length) return;
    const { x: dx, y: dy } = resultantPixels();
    const sx = isPhasorMode() ? CX : vectors[0].sx;
    const sy = isPhasorMode() ? CY : vectors[0].sy;
    const ex = sx + dx;
    const ey = sy + dy;

    // The two display options are independent: a square can remain visible
    // even when the resultant arrow itself is hidden.
    if (ui.showSquare.checked) drawSquareOnResultant(sx, sy, ex, ey);
    if (ui.showResult.checked) {
      drawArrow(sx, sy, ex, ey, {
        color: DARK, width: 4, alpha: 0.95,
        label: isPhasorMode() ? "z" : "R",
      });
      drawResultantPhaseArc(sx, sy, ex, ey);
    }
  }

  function drawPathPhaseExample() {
    if (!isPhasorMode()) return;
    const lam = wavelength();
    const ds = pathDifference();
    const phase = TAU * ds / lam;
    const wrapped = ((phase % TAU) + TAU) % TAU;
    const x = 82;
    const y = 82;
    const length = 50; // Keep the example arrow within its inset panel.

    ctx.save();
    ctx.fillStyle = "rgba(255, 255, 255, 0.86)";
    ctx.strokeStyle = "#d8e0ec";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.roundRect(22, 24, 190, 126, 16);
    ctx.fill();
    ctx.stroke();
    ctx.fillStyle = "#657286";
    ctx.font = "700 12px Inter, system-ui, sans-serif";
    ctx.fillText("Phase from Δs and λ", 40, 50);
    ctx.restore();

    drawLine(x - 46, y, x + 96, y, "#e2e8f0", 1.2);
    drawLine(x, y + 46, x, y - 46, "#e2e8f0", 1.2);
    drawArrow(x, y, x + length * Math.cos(wrapped), y - length * Math.sin(wrapped), {
      color: currentColor(), width: 3,
    });
    ctx.save();
    ctx.fillStyle = "#142033";
    ctx.font = "700 12px Inter, system-ui, sans-serif";
    ctx.fillText(`φ mod 2π = ${fmt(wrapped)} rad`, 40, 132);
    ctx.restore();
  }

  function drawPreview() {
    if (!previewVector) return;
    drawArrow(previewVector.sx, previewVector.sy, previewVector.ex, previewVector.ey, {
      color: previewVector.color, width: 2.2, alpha: 0.55, dashed: true,
    });
  }

  function drawAll() {
    drawGridAndAxes();
    drawPathPhaseExample();
    drawPhasorAdditionChain();
    vectors.forEach((vector, index) => drawVector(vector, index));
    drawPreview();
    drawResultant();
  }

  function pointToSegmentDistance(point, sx, sy, ex, ey) {
    const dx = ex - sx;
    const dy = ey - sy;
    const lengthSquared = dx * dx + dy * dy;
    if (lengthSquared === 0) return Math.hypot(point.x - sx, point.y - sy);
    const t = clamp(((point.x - sx) * dx + (point.y - sy) * dy) / lengthSquared, 0, 1);
    return Math.hypot(point.x - (sx + t * dx), point.y - (sy + t * dy));
  }

  function hitTest(point) {
    for (let i = vectors.length - 1; i >= 0; i -= 1) {
      const vector = vectors[i];
      if (distance(point, { x: vector.ex, y: vector.ey }) <= HANDLE_RADIUS + 4) {
        return { index: i, part: "end" };
      }
      if (!isPhasorMode() && distance(point, { x: vector.sx, y: vector.sy }) <= HANDLE_RADIUS + 4) {
        return { index: i, part: "start" };
      }
    }
    for (let i = vectors.length - 1; i >= 0; i -= 1) {
      const vector = vectors[i];
      if (pointToSegmentDistance(point, vector.sx, vector.sy, vector.ex, vector.ey) <= HIT_DISTANCE) {
        return { index: i, part: "body" };
      }
    }
    return { index: null, part: null };
  }

  function nearestSnapPoint(point, excludedIndex = null) {
    const candidates = [origin()];
    for (let i = vectors.length - 1; i >= 0; i -= 1) {
      if (i === excludedIndex) continue;
      const vector = vectors[i];
      candidates.push({ x: vector.ex, y: vector.ey });
      candidates.push({ x: vector.sx, y: vector.sy });
    }
    let nearest = null;
    let minDistance = SNAP_DISTANCE;
    for (const candidate of candidates) {
      const d = distance(point, candidate);
      if (d <= minDistance) {
        nearest = candidate;
        minDistance = d;
      }
    }
    return nearest;
  }

  function snapPoint(point, excludedIndex = null) {
    return nearestSnapPoint(point, excludedIndex) ?? point;
  }

  function snapWholeVector(sx, sy, ex, ey, excludedIndex = null) {
    const startTarget = nearestSnapPoint({ x: sx, y: sy }, excludedIndex);
    if (startTarget) {
      const dx = startTarget.x - sx;
      const dy = startTarget.y - sy;
      return { sx: sx + dx, sy: sy + dy, ex: ex + dx, ey: ey + dy };
    }
    const endTarget = nearestSnapPoint({ x: ex, y: ey }, excludedIndex);
    if (endTarget) {
      const dx = endTarget.x - ex;
      const dy = endTarget.y - ey;
      return { sx: sx + dx, sy: sy + dy, ex: ex + dx, ey: ey + dy };
    }
    return { sx, sy, ex, ey };
  }

  function pointerDown(event) {
    if (activePointerId !== null || (event.pointerType === "mouse" && event.button !== 0)) return;
    event.preventDefault();
    const pos = canvasPoint(event);
    const { index, part } = hitTest(pos);
    activePointerId = event.pointerId;
    canvas.setPointerCapture(event.pointerId);
    canvas.style.cursor = "grabbing";

    if (index !== null) {
      selectedIndex = index;
      dragStartPos = pos;
      dragOriginal = { ...vectors[index] };
      dragMode = part === "end" || part === "start"
        ? part : (isPhasorMode() ? "end" : "move");
      previewVector = null;
      updateReadouts();
      drawAll();
      return;
    }

    selectedIndex = null;
    dragMode = "new";
    dragStartPos = isPhasorMode() ? origin() : snapPoint(pos);
    dragOriginal = null;
    previewVector = {
      sx: dragStartPos.x, sy: dragStartPos.y,
      ex: pos.x, ey: pos.y,
      color: isPhasorMode() ? currentColor() : BLUE,
    };
    drawAll();
  }

  function pointerMove(event) {
    const pos = canvasPoint(event);
    if (activePointerId === null) {
      const { part } = hitTest(pos);
      canvas.style.cursor = part === "start" || part === "end"
        ? "grab" : part === "body" ? "pointer" : "crosshair";
      return;
    }
    if (event.pointerId !== activePointerId) return;
    event.preventDefault();

    if (dragMode === "new" && previewVector) {
      const end = snapPoint(pos);
      previewVector.ex = end.x;
      previewVector.ey = end.y;
      drawAll();
      return;
    }

    if (selectedIndex === null || !dragOriginal) return;
    const vector = vectors[selectedIndex];

    if (dragMode === "end") {
      const end = snapPoint(pos, selectedIndex);
      vector.ex = end.x;
      vector.ey = end.y;
      if (isPhasorMode()) {
        vector.sx = CX;
        vector.sy = CY;
      }
    } else if (dragMode === "start" && !isPhasorMode()) {
      const start = snapPoint(pos, selectedIndex);
      vector.sx = start.x;
      vector.sy = start.y;
    } else if (dragMode === "move" && !isPhasorMode()) {
      const dx = pos.x - dragStartPos.x;
      const dy = pos.y - dragStartPos.y;
      Object.assign(vector, snapWholeVector(
        dragOriginal.sx + dx, dragOriginal.sy + dy,
        dragOriginal.ex + dx, dragOriginal.ey + dy,
        selectedIndex,
      ));
    }
    updateReadouts();
    drawAll();
  }

  function pointerEnd(event, cancel = false) {
    if (event.pointerId !== activePointerId) return;

    if (!cancel && dragMode === "new" && previewVector) {
      const length = Math.hypot(previewVector.ex - previewVector.sx, previewVector.ey - previewVector.sy);
      if (length >= MIN_LENGTH) {
        vectors.push({ ...previewVector });
        selectedIndex = vectors.length - 1;
      }
    }
    activePointerId = null;
    dragMode = null;
    dragStartPos = null;
    dragOriginal = null;
    previewVector = null;
    canvas.style.cursor = "crosshair";
    if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
    updateReadouts();
    drawAll();
  }

  function makeVectorFromPolar(x, y, length, angleDegrees, color) {
    const angle = angleDegrees * Math.PI / 180;
    return {
      sx: x, sy: y,
      ex: x + length * Math.cos(angle),
      ey: y - length * Math.sin(angle),
      color,
    };
  }

  function addPolarSequence(lengths, angles) {
    vectors = [];
    selectedIndex = null;
    if (isPhasorMode()) {
      for (let i = 0; i < lengths.length; i += 1) {
        vectors.push(makeVectorFromPolar(CX, CY, lengths[i], angles[i], currentColor()));
      }
    } else {
      let x = CX - 120;
      let y = CY + 50;
      for (let i = 0; i < lengths.length; i += 1) {
        const vector = makeVectorFromPolar(x, y, lengths[i], angles[i], BLUE);
        vectors.push(vector);
        x = vector.ex;
        y = vector.ey;
      }
    }
  }

  function applyPreset(name) {
    if (name === "free") return;
    switch (name) {
      case "constructive":
        addPolarSequence([135, 135], [0, 0]);
        break;
      case "destructive":
        addPolarSequence([135, 135], [0, 180]);
        break;
      case "right_angle":
        addPolarSequence([135, 135], [0, 90]);
        break;
      case "six_steps":
        addPolarSequence(Array(6).fill(82), [0, 18, 36, 54, 72, 90]);
        break;
      case "circle_cancel":
        addPolarSequence(Array(12).fill(75), Array.from({ length: 12 }, (_, i) => i * 30));
        break;
      case "near_phase":
        addPolarSequence(Array(12).fill(35), Array.from({ length: 12 }, (_, i) => -24 + i * 48 / 11));
        break;
      default:
        return;
    }
    updateReadouts();
    drawAll();
  }

  function removeLast() {
    if (vectors.length) vectors.pop();
    selectedIndex = null;
    ui.preset.value = "free";
    updateReadouts();
    drawAll();
  }

  function deleteSelected() {
    if (selectedIndex !== null && selectedIndex < vectors.length) {
      vectors.splice(selectedIndex, 1);
      selectedIndex = null;
      ui.preset.value = "free";
    }
    updateReadouts();
    drawAll();
  }

  function clearAll() {
    vectors = [];
    selectedIndex = null;
    previewVector = null;
    ui.preset.value = "free";
    updateReadouts();
    drawAll();
  }

  function updateColorUI() {
    const { rgb, name } = wavelengthToColor(wavelength());
    ui.wavelengthReadout.textContent = `${wavelength()} nm`;
    ui.pathReadout.textContent = `${pathDifference()} nm`;
    ui.colorPreview.style.background = rgb;
    ui.colorName.textContent = name;
    if (isPhasorMode()) {
      for (const vector of vectors) vector.color = rgb;
    }
    updateReadouts();
    drawAll();
  }

  function updateModeUI() {
    if (isPhasorMode()) {
      ui.badge.textContent = "Phasor mode";
      ui.hint.textContent = "Draw phasors from the origin. Length and direction define amplitude and phase.";
      ui.phasorControls.classList.remove("hidden");
      ui.sumHeading.textContent = "2. Phasor addition";
    } else {
      ui.badge.textContent = "Vector mode";
      ui.hint.textContent = "Click and drag to draw. Arrows can snap together.";
      ui.phasorControls.classList.add("hidden");
      ui.sumHeading.textContent = "2. Vector addition";
    }
    updateColorUI();
  }

  function updateReadouts() {
    const { re, im } = complexResultant();
    const magnitude = Math.hypot(re, im);
    const magnitudeSquared = magnitude ** 2;
    const phase = phaseDegrees(re, im);

    ui.countReadout.textContent = String(vectors.length);
    ui.resultReadout.textContent = isPhasorMode()
      ? `|zₜₒₜₐₗ| = ${fmt(magnitude)}` : `|R| = ${fmt(magnitude)}`;
    ui.phaseReadout.textContent = !ui.showPhase.checked
      ? "–" : phase === null ? "φ = –" : `φ = ${fmt(phase, 1)}°`;
    ui.squareReadout.textContent = !ui.showSquare.checked
      ? "–" : `${isPhasorMode() ? "|zₜₒₜₐₗ|²" : "|R|²"} = ${fmt(magnitudeSquared)}`;

    ui.sumFormula.innerHTML = isPhasorMode()
      ? `z<sub>total</sub> = Σ z<sub>n</sub> = ${complexString(re, im)}`
      : `R = Σ v<sub>n</sub> = (${fmt(re)}; ${fmt(im)})`;
    ui.magnitudeFormula.innerHTML = isPhasorMode()
      ? `|z<sub>total</sub>|² = ${fmt(magnitudeSquared)}`
      : `|R|² = ${fmt(magnitudeSquared)}`;

    const lam = wavelength();
    const ds = pathDifference();
    const phaseRadians = TAU * ds / lam;
    const phaseMod = ((phaseRadians % TAU) + TAU) % TAU;
    ui.formulaWavelength.textContent = `${lam} nm`;
    ui.formulaPath.textContent = `${ds} nm`;
    ui.formulaPhase.textContent = `${fmt(phaseMod)} rad`;
    ui.pathPhaseFormula.textContent =
      `φ = 2π · Δs / λ = 2π · ${ds} nm / ${lam} nm = ${fmt(phaseRadians)} rad`;
  }

  function bindEvents() {
    canvas.addEventListener("pointerdown", pointerDown);
    canvas.addEventListener("pointermove", pointerMove);
    canvas.addEventListener("pointerup", (event) => pointerEnd(event));
    canvas.addEventListener("pointercancel", (event) => pointerEnd(event, true));
    canvas.addEventListener("lostpointercapture", (event) => {
      if (activePointerId === event.pointerId) pointerEnd(event, true);
    });
    canvas.addEventListener("pointerleave", () => {
      if (activePointerId === null) canvas.style.cursor = "crosshair";
    });

    ui.mode.addEventListener("change", () => {
      clearAll();
      updateModeUI();
    });
    ui.preset.addEventListener("change", () => applyPreset(ui.preset.value));
    ui.undo.addEventListener("click", removeLast);
    ui.deleteSelected.addEventListener("click", deleteSelected);
    ui.clearAll.addEventListener("click", clearAll);

    for (const checkbox of [
      ui.showResult, ui.showPhase, ui.showSquare, ui.showIndividual, ui.showAxes,
    ]) {
      checkbox.addEventListener("change", () => {
        updateReadouts();
        drawAll();
      });
    }
    ui.showEquations.addEventListener("change", () => {
      ui.formulaPanel.classList.toggle("hidden", !ui.showEquations.checked);
      updateReadouts();
      drawAll();
    });
    ui.wavelength.addEventListener("input", updateColorUI);
    ui.pathDifference.addEventListener("input", updateColorUI);

    document.addEventListener("keydown", (event) => {
      // Do not intercept text editing or native select/slider keyboard control.
      if (event.target.closest("input, select, textarea, [contenteditable]")) return;
      if (event.key === "Backspace" || event.key === "Delete") {
        event.preventDefault();
        deleteSelected();
      } else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z") {
        event.preventDefault();
        removeLast();
      }
    });
  }

  bindEvents();
  updateModeUI();
  ui.formulaPanel.classList.toggle("hidden", !ui.showEquations.checked);
})();
