/**
 * Phasor Formalism – Optical Experiments
 *
 * Standalone JavaScript port of the three original PyScript modules:
 *   1. Thin glass film: two equal field contributions, normal incidence.
 *   2. Mirror: equal-weight contributions from discrete mirror regions.
 *   3. Single/double slit: discrete phasors and Fraunhofer far-field intensity.
 *
 * The drawn paths represent contributions to a field amplitude, not measured
 * trajectories of individual photons. The thin-film reflectance is a simplified
 * illustrative model, not a Fresnel-coefficient calculation.
 *
 * No libraries, build tools, or Python runtime required.
 */
(() => {
  "use strict";

  const byId = (id) => document.getElementById(id);
  const canvas = byId("experiment-canvas");
  const ctx = canvas.getContext("2d");
  const WIDTH = canvas.width;
  const HEIGHT = canvas.height;
  const GEOMETRY = [28, 26, 680, 338];
  const PHASOR = [734, 26, 438, 338];
  const GRAPH = [28, 390, 1144, 300];
  const TAU = 2 * Math.PI;

  const INK = "#172033";
  const MUTED = "#68778d";
  const LINE = "#dce4ef";
  const ACCENT = "#4257ff";
  const ACCENT_DARK = "#2638c8";
  const RESULT = "#151a2d";

  const controls = {
    hint: byId("interaction-hint"),
    status: byId("app-status"),
    wavelength: byId("wavelength-slider"),
    wavelengthReadout: byId("wavelength-readout"),
    colorPreview: byId("color-preview"),
    colorName: byId("color-name"),
    thickness: byId("thickness-slider"),
    thicknessReadout: byId("thickness-readout"),
    refractiveIndex: byId("index-slider"),
    indexReadout: byId("index-readout"),
    compare: byId("compare-toggle"),
    compareControls: byId("compare-controls"),
    compareWavelength: byId("compare-wavelength-slider"),
    compareWavelengthReadout: byId("compare-wavelength-readout"),
    segments: byId("segment-slider"),
    segmentReadout: byId("segment-readout"),
    classic: byId("classic-toggle"),
    pathGraph: byId("path-graph-toggle"),
    slitType: byId("slit-select"),
    slitWidth: byId("slit-width-slider"),
    slitWidthReadout: byId("slit-width-readout"),
    slitDistanceControls: byId("slit-distance-controls"),
    slitDistance: byId("slit-distance-slider"),
    slitDistanceReadout: byId("slit-distance-readout"),
    angle: byId("angle-slider"),
    angleReadout: byId("angle-readout"),
    slitSegments: byId("slit-segments-slider"),
    slitSegmentsReadout: byId("slit-segments-readout"),
    separateRow: byId("separate-row"),
    separateSlits: byId("separate-slits-toggle"),
    formulaToggle: byId("formula-toggle"),
    formulaPanel: byId("formula-panel"),
    formulaTitle: byId("formula-title"),
    formulaNote: byId("formula-model-note"),
    formulaContent: byId("formula-content"),
    readoutLabels: [1, 2, 3, 4].map((i) => byId(`readout-label-${i}`)),
    readoutValues: [1, 2, 3, 4].map((i) => byId(`readout-value-${i}`)),
  };

  const state = {
    experiment: "film",
    hoverSegment: null,
    dragTarget: null,
    source: [-3.7, 2.7],   // mirror-model coordinates (µm)
    detector: [3.4, 2.25], // mirror-model coordinates (µm)
  };

  function value(input) { return Number(input.value); }
  function clamp(x, low, high) { return Math.max(low, Math.min(high, x)); }
  function fmt(x, digits = 2) {
    if (!Number.isFinite(x)) return "–";
    return (Math.abs(x) < 0.5 * Math.pow(10, -digits) ? 0 : x).toFixed(digits);
  }
  function wavelengthNm() { return value(controls.wavelength); }
  function wavelengthUm() { return wavelengthNm() / 1000; }
  function phaseMod(phi) { return ((phi % TAU) + TAU) % TAU; }
  function sinc(x) { return Math.abs(x) < 1e-10 ? 1 : Math.sin(x) / x; }
  function c(re = 0, im = 0) { return { re, im }; }
  function cadd(a, b) { return c(a.re + b.re, a.im + b.im); }
  function cpolar(amplitude, phase) {
    return c(amplitude * Math.cos(phase), amplitude * Math.sin(phase));
  }
  function cmag(z) { return Math.hypot(z.re, z.im); }
  function cmag2(z) { return z.re * z.re + z.im * z.im; }
  function csum(values) {
    let re = 0;
    let im = 0;
    for (const z of values) { re += z.re; im += z.im; }
    return c(re, im);
  }

  // Qualitative sRGB approximation, not a physical spectral color simulation.
  const COLOR_ANCHORS = [
    [380, [108, 45, 190], "violet"],
    [440, [48, 78, 230], "blue"],
    [490, [25, 170, 213], "cyan"],
    [520, [42, 190, 93], "green"],
    [570, [216, 205, 34], "yellow"],
    [600, [246, 139, 32], "orange"],
    [650, [224, 55, 45], "red"],
    [740, [139, 25, 40], "deep red"],
  ];
  function wavelengthColor(wavelength) {
    const w = clamp(wavelength, COLOR_ANCHORS[0][0], COLOR_ANCHORS.at(-1)[0]);
    for (let i = 0; i < COLOR_ANCHORS.length - 1; i++) {
      const a = COLOR_ANCHORS[i];
      const b = COLOR_ANCHORS[i + 1];
      if (w >= a[0] && w <= b[0]) {
        const t = (w - a[0]) / (b[0] - a[0]);
        const rgb = a[1].map((n, j) => Math.round(n + (b[1][j] - n) * t));
        return { rgb, name: t < 0.5 ? a[2] : b[2] };
      }
    }
    const last = COLOR_ANCHORS.at(-1);
    return { rgb: last[1], name: last[2] };
  }
  function rgbString(rgb, alpha = null) {
    return alpha === null ? `rgb(${rgb.join(", ")})` : `rgba(${rgb.join(", ")}, ${alpha})`;
  }
  function currentColor() { return rgbString(wavelengthColor(wavelengthNm()).rgb); }

  // -------------------------------------------------------------------------
  // Shared canvas drawing primitives
  // -------------------------------------------------------------------------
  function panel(rect, title, suffix = "") {
    const [x, y, w, h] = rect;
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(x, y, w, h);
    ctx.strokeStyle = LINE;
    ctx.lineWidth = 1;
    ctx.strokeRect(x + 0.5, y + 0.5, w - 1, h - 1);
    ctx.fillStyle = INK;
    ctx.font = "800 16px Inter, system-ui, sans-serif";
    ctx.textAlign = "left";
    ctx.fillText(title, x + 18, y + 27);
    if (suffix) {
      ctx.fillStyle = MUTED;
      ctx.font = "600 12px Inter, system-ui, sans-serif";
      ctx.fillText(suffix, x + w - 18 - ctx.measureText(suffix).width, y + 26);
    }
  }
  function line(x1, y1, x2, y2, color = INK, width = 1.5, alpha = 1) {
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
  function dot(x, y, radius, color, stroke = "#ffffff", strokeWidth = 2) {
    ctx.save();
    ctx.beginPath();
    ctx.arc(x, y, radius, 0, TAU);
    ctx.fillStyle = color;
    ctx.fill();
    if (strokeWidth) {
      ctx.strokeStyle = stroke;
      ctx.lineWidth = strokeWidth;
      ctx.stroke();
    }
    ctx.restore();
  }
  function label(text, x, y, color = MUTED, size = 12, weight = 650, align = "left") {
    ctx.save();
    ctx.fillStyle = color;
    ctx.font = `${weight} ${size}px Inter, system-ui, sans-serif`;
    ctx.textAlign = align;
    ctx.fillText(String(text), x, y);
    ctx.restore();
  }
  function arrow(x1, y1, x2, y2, color = ACCENT, width = 3, head = 9, alpha = 1) {
    const dx = x2 - x1;
    const dy = y2 - y1;
    if (Math.hypot(dx, dy) < 1e-8) return;
    const angle = Math.atan2(dy, dx);
    ctx.save();
    ctx.globalAlpha = alpha;
    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    ctx.lineWidth = width;
    ctx.lineCap = "round";
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(x2, y2);
    ctx.lineTo(x2 - head * Math.cos(angle - 0.48), y2 - head * Math.sin(angle - 0.48));
    ctx.lineTo(x2 - head * Math.cos(angle + 0.48), y2 - head * Math.sin(angle + 0.48));
    ctx.closePath();
    ctx.fill();
    ctx.restore();
  }
  function chartAxes(rect, xLabel, yLabel, yTicks = null) {
    const [x, y, w, h] = rect;
    const left = x + 62;
    const right = x + w - 22;
    const top = y + 48;
    const bottom = y + h - 42;
    if (yTicks) {
      for (const [v, text] of yTicks) {
        const py = bottom - v * (bottom - top);
        line(left, py, right, py, LINE, 1);
        label(text, left - 10, py + 4, MUTED, 11, 600, "right");
      }
    }
    line(left, bottom, right, bottom, MUTED, 1.2);
    line(left, top, left, bottom, MUTED, 1.2);
    label(xLabel, (left + right) / 2, y + h - 13, MUTED, 12, 700, "center");
    label(yLabel, left, y + 39, MUTED, 12, 700);
    return [left, top, right, bottom];
  }
  function polyline(points, color, width = 2.2, alpha = 1) {
    if (points.length === 0) return;
    ctx.save();
    ctx.globalAlpha = alpha;
    ctx.strokeStyle = color;
    ctx.lineWidth = width;
    ctx.lineJoin = "round";
    ctx.beginPath();
    ctx.moveTo(points[0][0], points[0][1]);
    for (let i = 1; i < points.length; i++) ctx.lineTo(points[i][0], points[i][1]);
    ctx.stroke();
    ctx.restore();
  }
  function drawPhasorAxes(rect) {
    const [x, y, w, h] = rect;
    const cx = x + w / 2;
    const cy = y + h / 2 + 10;
    line(x + 34, cy, x + w - 25, cy, LINE, 1);
    line(cx, y + 48, cx, y + h - 25, LINE, 1);
    label("Re", x + w - 32, cy - 8, MUTED, 11, 700);
    label("Im", cx + 8, y + 58, MUTED, 11, 700);
    return [cx, cy];
  }
  function drawPhasorChain(values, rect, color, highlight = null, resultColor = RESULT) {
    const [x, y, w, h] = rect;
    const sums = [c()];
    for (const z of values) sums.push(cadd(sums[sums.length - 1], z));
    const res = sums[sums.length - 1];
    const reValues = sums.map((z) => z.re);
    const imValues = sums.map((z) => z.im);
    const minRe = Math.min(...reValues, 0);
    const maxRe = Math.max(...reValues, 0);
    const minIm = Math.min(...imValues, 0);
    const maxIm = Math.max(...imValues, 0);
    const span = Math.max(maxRe - minRe, maxIm - minIm, 0.35);
    const scale = Math.min((w - 88) / span, (h - 104) / span);
    const cx = x + w / 2 - (maxRe + minRe) / 2 * scale;
    const cy = y + h / 2 + 15 + (maxIm + minIm) / 2 * scale;
    line(x + 24, cy, x + w - 24, cy, LINE, 1);
    line(cx, y + 48, cx, y + h - 22, LINE, 1);
    values.forEach((z, i) => {
      const start = sums[i];
      const end = sums[i + 1];
      const selected = i === highlight;
      arrow(
        cx + start.re * scale, cy - start.im * scale,
        cx + end.re * scale, cy - end.im * scale,
        selected ? ACCENT_DARK : color,
        selected ? 3.8 : 1.7,
        selected ? 8 : 5,
        selected ? 1 : 0.72
      );
    });
    arrow(cx, cy, cx + res.re * scale, cy - res.im * scale, resultColor, 4.2, 11);
    dot(cx, cy, 3.4, resultColor, "#ffffff", 0);
    return res;
  }
  function clearCanvas() {
    ctx.clearRect(0, 0, WIDTH, HEIGHT);
    ctx.fillStyle = "#f9fbfe";
    ctx.fillRect(0, 0, WIDTH, HEIGHT);
  }

  // -------------------------------------------------------------------------
  // Experiment 1: Thin glass film (illustrative two-contribution model)
  // -------------------------------------------------------------------------
  function filmValues(lam = null, thickness = null, refractiveIndex = null) {
    const wavelength = lam ?? wavelengthNm();
    const d = thickness ?? value(controls.thickness);
    const n = refractiveIndex ?? value(controls.refractiveIndex);
    const deltaPhi = 4 * Math.PI * n * d / wavelength + Math.PI;
    const e1 = c(0.2, 0);
    const e2 = cpolar(0.2, deltaPhi);
    const total = cadd(e1, e2);
    return { deltaPhi, e1, e2, total, reflectance: cmag2(total) };
  }
  function drawFilmGeometry() {
    const [x, y, w] = GEOMETRY;
    panel(GEOMETRY, "Optical setup", "normal incidence");
    const color = currentColor();
    const d = value(controls.thickness);
    const layerHeight = 42 + d / 1200 * 142;
    const top = y + 146;
    const bottom = top + layerHeight;
    ctx.fillStyle = "rgba(104, 169, 225, 0.18)";
    ctx.fillRect(x + 65, top, w - 130, layerHeight);
    line(x + 65, top, x + w - 65, top, "#6b8cac", 2);
    line(x + 65, bottom, x + w - 65, bottom, "#6b8cac", 2);
    label("Air", x + 78, top - 12, MUTED, 12, 700);
    label(`Glass  n = ${fmt(value(controls.refractiveIndex), 2)}`, x + 78, top + 25, MUTED, 12, 700);

    // Separate schematic paths: upper-surface and lower-surface reflection.
    const rayX1 = x + 285;
    const rayX2 = x + 420;
    arrow(rayX1, y + 65, rayX1, top - 3, color, 3.2, 10);
    arrow(rayX1, top - 3, rayX1, y + 72, color, 3.2, 10, 0.72);
    label("E₁", rayX1 - 19, y + 88, color, 13, 850);
    arrow(rayX2, y + 65, rayX2, top - 3, color, 3.2, 10);
    line(rayX2, top, rayX2, bottom, color, 3.2);
    arrow(rayX2, bottom, rayX2, top + 5, color, 3.2, 10, 0.72);
    arrow(rayX2, top - 5, rayX2, y + 72, color, 3.2, 10, 0.72);
    label("E₂", rayX2 + 17, y + 88, color, 13, 850);
    const bx = x + w - 95;
    line(bx, top, bx, bottom, MUTED, 1.4);
    line(bx - 7, top, bx + 7, top, MUTED, 1.4);
    line(bx - 7, bottom, bx + 7, bottom, MUTED, 1.4);
    label("d", bx + 12, (top + bottom) / 2 + 4, INK, 14, 800);
  }
  function drawFilmPhasors() {
    panel(PHASOR, "Phasor addition");
    const { deltaPhi, e1, e2, total } = filmValues();
    const [x, y, , h] = PHASOR;
    const [cx, cy] = drawPhasorAxes(PHASOR);
    const scale = 520;
    const p1 = [cx + e1.re * scale, cy - e1.im * scale];
    const p2 = [p1[0] + e2.re * scale, p1[1] - e2.im * scale];
    const color = currentColor();
    arrow(cx, cy, p1[0], p1[1], color, 4, 11);
    arrow(p1[0], p1[1], p2[0], p2[1], color, 4, 11, 0.82);
    arrow(cx, cy, cx + total.re * scale, cy - total.im * scale, RESULT, 4.5, 12);
    label("E₁", (cx + p1[0]) / 2, cy - 12, color, 13, 850, "center");
    label("E₂", (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2 - 11, color, 13, 850, "center");
    label("E", cx + total.re * scale + 10, cy - total.im * scale - 8, RESULT, 14, 900);
    label(`Δφ = ${fmt(phaseMod(deltaPhi), 2)} rad`, x + 18, y + h - 18, MUTED, 12, 700);
  }
  function drawFilmGraph() {
    panel(GRAPH, "Model reflectance", "R(d)");
    const [left, top, right, bottom] = chartAxes(
      GRAPH, "Film thickness d (nm)", "R", [[0, "0%"], [0.5, "8%"], [1, "16%"]]
    );
    const maxD = 1200;
    const lam = wavelengthNm();
    const color = currentColor();
    function curvePoints(curveLam) {
      const points = [];
      for (let i = 0; i <= 360; i++) {
        const d = maxD * i / 360;
        const reflection = filmValues(curveLam, d).reflectance;
        points.push([
          left + d / maxD * (right - left),
          bottom - reflection / 0.16 * (bottom - top),
        ]);
      }
      return points;
    }
    polyline(curvePoints(lam), color, 3);
    label("0", left, bottom + 18, MUTED, 11, 600, "center");
    label("600", (left + right) / 2, bottom + 18, MUTED, 11, 600, "center");
    label("1200", right, bottom + 18, MUTED, 11, 600, "center");
    if (controls.compare.checked) {
      const lam2 = value(controls.compareWavelength);
      const color2 = rgbString(wavelengthColor(lam2).rgb);
      polyline(curvePoints(lam2), color2, 2.3, 0.85);
      label(`λ₂ = ${Math.round(lam2)} nm`, right - 8, top + 18, color2, 12, 800, "right");
    }
    const d = value(controls.thickness);
    const reflection = filmValues().reflectance;
    const px = left + d / maxD * (right - left);
    const py = bottom - reflection / 0.16 * (bottom - top);
    line(px, top, px, bottom, color, 1.2, 0.35);
    dot(px, py, 6, color);
  }
  function drawFilm() {
    drawFilmGeometry();
    drawFilmPhasors();
    drawFilmGraph();
  }

  // -------------------------------------------------------------------------
  // Experiment 2: Mirror and stationary optical phase
  // -------------------------------------------------------------------------
  const MIRROR_X_MIN = -6;
  const MIRROR_X_MAX = 6;
  function mirrorToCanvas(modelX, modelHeight) {
    const [gx, gy, gw, gh] = GEOMETRY;
    const px = gx + 62 + (modelX - MIRROR_X_MIN) / (MIRROR_X_MAX - MIRROR_X_MIN) * (gw - 124);
    const mirrorY = gy + gh - 58;
    const py = mirrorY - modelHeight * 72;
    return [px, py];
  }
  function canvasToMirror(px, py) {
    const [gx, gy, gw, gh] = GEOMETRY;
    const modelX = MIRROR_X_MIN + (px - gx - 62) / (gw - 124) * (MIRROR_X_MAX - MIRROR_X_MIN);
    const mirrorY = gy + gh - 58;
    const modelH = (mirrorY - py) / 72;
    return [clamp(modelX, -5.6, 5.6), clamp(modelH, 0.45, 3.55)];
  }
  function mirrorSegments() {
    const count = Math.round(value(controls.segments));
    const step = (MIRROR_X_MAX - MIRROR_X_MIN) / count;
    return Array.from({ length: count }, (_, i) => MIRROR_X_MIN + (i + 0.5) * step);
  }
  function mirrorPathLength(x) {
    const [qx, qh] = state.source;
    const [dx, dh] = state.detector;
    return Math.hypot(x - qx, qh) + Math.hypot(dx - x, dh);
  }
  function classicReflectionX() {
    const [qx, qh] = state.source;
    const [dx, dh] = state.detector;
    return (qx * dh + dx * qh) / (qh + dh);
  }
  function mirrorPhasors() {
    const xs = mirrorSegments();
    const ref = Math.min(...xs.map(mirrorPathLength));
    const k = TAU / wavelengthUm();
    const amplitude = 1 / xs.length;
    const values = xs.map((x) => cpolar(amplitude, k * (mirrorPathLength(x) - ref)));
    return { xs, values };
  }
  function drawMirrorGeometry() {
    panel(GEOMETRY, "Optical setup", "drag source or detector");
    const [gx, gy, gw, gh] = GEOMETRY;
    const mirrorY = gy + gh - 58;
    const xLeft = mirrorToCanvas(MIRROR_X_MIN, 0)[0];
    const xRight = mirrorToCanvas(MIRROR_X_MAX, 0)[0];
    line(xLeft, mirrorY, xRight, mirrorY, "#263a55", 5);
    const color = currentColor();
    const { xs } = mirrorPhasors();
    const sourcePx = mirrorToCanvas(...state.source);
    const detectorPx = mirrorToCanvas(...state.detector);
    for (let i = 0; i < xs.length; i++) {
      const mirrorPx = mirrorToCanvas(xs[i], 0);
      const selected = i === state.hoverSegment;
      const width = selected ? 2.7 : 1;
      const alpha = selected ? 0.95 : 0.16;
      line(sourcePx[0], sourcePx[1], mirrorPx[0], mirrorPx[1], color, width, alpha);
      line(mirrorPx[0], mirrorPx[1], detectorPx[0], detectorPx[1], color, width, alpha);
      if (selected) dot(mirrorPx[0], mirrorPx[1], 5, ACCENT_DARK);
    }
    if (controls.classic.checked) {
      const starPx = mirrorToCanvas(classicReflectionX(), 0);
      line(sourcePx[0], sourcePx[1], starPx[0], starPx[1], RESULT, 3, 0.8);
      line(starPx[0], starPx[1], detectorPx[0], detectorPx[1], RESULT, 3, 0.8);
      dot(starPx[0], starPx[1], 5, RESULT);
      label("specular", starPx[0], mirrorY + 23, RESULT, 11, 800, "center");
    }
    dot(sourcePx[0], sourcePx[1], 10, color);
    dot(detectorPx[0], detectorPx[1], 10, RESULT);
    label("S", sourcePx[0], sourcePx[1] - 16, color, 14, 900, "center");
    label("D", detectorPx[0], detectorPx[1] - 16, RESULT, 14, 900, "center");
    label("Mirror", xLeft, mirrorY + 23, MUTED, 11, 700);
  }
  function drawMirrorPhasors() {
    panel(PHASOR, "Phasor chain");
    const { values } = mirrorPhasors();
    drawPhasorChain(values, PHASOR, currentColor(), state.hoverSegment);
  }
  function drawMirrorGraph() {
    if (controls.pathGraph.checked) {
      panel(GRAPH, "Optical path length", "stationary point");
      const xs = Array.from({ length: 361 }, (_, i) => MIRROR_X_MIN + i * (MIRROR_X_MAX - MIRROR_X_MIN) / 360);
      const lengths = xs.map(mirrorPathLength);
      const minL = Math.min(...lengths);
      const maxL = Math.max(...lengths);
      const [left, top, right, bottom] = chartAxes(GRAPH, "Mirror position x (µm)", "L(x)");
      const points = xs.map((x, i) => [
        left + (x - MIRROR_X_MIN) / (MIRROR_X_MAX - MIRROR_X_MIN) * (right - left),
        bottom - (lengths[i] - minL) / Math.max(maxL - minL, 1e-9) * (bottom - top),
      ]);
      polyline(points, ACCENT, 3);
      const star = classicReflectionX();
      const px = left + (star - MIRROR_X_MIN) / (MIRROR_X_MAX - MIRROR_X_MIN) * (right - left);
      const py = bottom - (mirrorPathLength(star) - minL) / Math.max(maxL - minL, 1e-9) * (bottom - top);
      dot(px, py, 6, RESULT);
      label("dL/dx = 0", px + 12, py - 10, RESULT, 12, 850);
      label("−6", left, bottom + 18, MUTED, 11, 600, "center");
      label("0", (left + right) / 2, bottom + 18, MUTED, 11, 600, "center");
      label("6", right, bottom + 18, MUTED, 11, 600, "center");
    } else {
      panel(GRAPH, "Total contribution", "squared magnitude");
      const { values } = mirrorPhasors();
      const intensity = cmag2(csum(values));
      const [gx, gy, gw] = GRAPH;
      const barLeft = gx + 145;
      const barRight = gx + gw - 145;
      const barY = gy + 154;
      ctx.fillStyle = "#e8edf5";
      ctx.fillRect(barLeft, barY, barRight - barLeft, 28);
      ctx.fillStyle = currentColor();
      ctx.fillRect(barLeft, barY, (barRight - barLeft) * intensity, 28);
      label("0", barLeft, barY + 51, MUTED, 11, 600, "center");
      label("1", barRight, barY + 51, MUTED, 11, 600, "center");
      label(`|E|² = ${fmt(intensity, 3)}`, (barLeft + barRight) / 2, barY - 28, INK, 22, 850, "center");
    }
  }
  function drawMirror() {
    drawMirrorGeometry();
    drawMirrorPhasors();
    drawMirrorGraph();
  }

  // -------------------------------------------------------------------------
  // Experiment 3: Single- and double-slit Fraunhofer diffraction
  // -------------------------------------------------------------------------
  function diffractionType() { return controls.slitType.value; }
  function diffractionPositions() {
    const totalCount = Math.round(value(controls.slitSegments));
    const slitWidth = value(controls.slitWidth);
    if (diffractionType() === "single") {
      return Array.from({ length: totalCount }, (_, i) => ({
        x: -slitWidth / 2 + (i + 0.5) * slitWidth / totalCount,
        slit: 0,
      }));
    }
    const countPerSlit = Math.max(2, Math.floor(totalCount / 2));
    const distance = value(controls.slitDistance);
    const positions = [];
    [-distance / 2, distance / 2].forEach((center, slit) => {
      for (let i = 0; i < countPerSlit; i++) {
        positions.push({
          x: center - slitWidth / 2 + (i + 0.5) * slitWidth / countPerSlit,
          slit,
        });
      }
    });
    return positions;
  }
  function diffractionPhasors(thetaDeg = null) {
    const theta = (thetaDeg ?? value(controls.angle)) * Math.PI / 180;
    const positions = diffractionPositions();
    const amplitude = 1 / positions.length;
    const k = TAU / wavelengthUm();
    const tagged = positions.map(({ x, slit }) => ({
      z: cpolar(amplitude, k * x * Math.sin(theta)),
      slit,
    }));
    return { positions, tagged };
  }
  function diffractionIntensity(thetaDeg) {
    const theta = thetaDeg * Math.PI / 180;
    const lam = wavelengthUm();
    const width = value(controls.slitWidth);
    const beta = Math.PI * width * Math.sin(theta) / lam;
    const envelope = sinc(beta) ** 2;
    if (diffractionType() === "single") return envelope;
    const distance = value(controls.slitDistance);
    const alpha = Math.PI * distance * Math.sin(theta) / lam;
    return envelope * Math.cos(alpha) ** 2;
  }
  function apertureScale() {
    const width = value(controls.slitWidth);
    const fullExtent = width + (diffractionType() === "double" ? value(controls.slitDistance) : 0);
    return Math.min(3.9, 220 / Math.max(fullExtent, 1));
  }
  function diffractionAperturesCanvas() {
    const centerY = GEOMETRY[1] + GEOMETRY[3] / 2 + 8;
    const width = value(controls.slitWidth);
    const scale = apertureScale();
    if (diffractionType() === "single") {
      return [[centerY - width * scale / 2, centerY + width * scale / 2]];
    }
    const distance = value(controls.slitDistance);
    return [
      [centerY + (-distance / 2 - width / 2) * scale,
        centerY + (-distance / 2 + width / 2) * scale],
      [centerY + (distance / 2 - width / 2) * scale,
        centerY + (distance / 2 + width / 2) * scale],
    ];
  }
  function drawDiffractionGeometry() {
    panel(GEOMETRY, "Optical setup", "drag detector on screen");
    const [gx, gy, gw, gh] = GEOMETRY;
    const color = currentColor();
    const apertureX = gx + 285;
    const screenX = gx + gw - 65;
    const centerY = gy + gh / 2 + 8;
    const screenTop = gy + 60;
    const screenBottom = gy + gh - 35;
    for (const offset of [0, 34, 68]) {
      const xWave = gx + 70 + offset;
      line(xWave, gy + 72, xWave, gy + gh - 48, color, 2, 0.45);
    }
    arrow(gx + 80, centerY, apertureX - 18, centerY, color, 3, 10);
    const intervals = diffractionAperturesCanvas().sort((a, b) => a[0] - b[0]);
    let currentY = screenTop;
    ctx.fillStyle = "#263a55";
    for (const [openingTop, openingBottom] of intervals) {
      ctx.fillRect(apertureX - 7, currentY, 14, Math.max(0, openingTop - currentY));
      currentY = openingBottom;
    }
    ctx.fillRect(apertureX - 7, currentY, 14, Math.max(0, screenBottom - currentY));
    label("Aperture", apertureX, screenBottom + 22, MUTED, 11, 700, "center");
    line(screenX, screenTop, screenX, screenBottom, "#263a55", 5);
    const thetaDeg = value(controls.angle);
    const detectorY = clamp(centerY - thetaDeg * 12.2, screenTop + 4, screenBottom - 4);
    const { positions } = diffractionPhasors();
    const positionScale = apertureScale();
    const stride = Math.max(1, Math.floor(positions.length / 16));
    positions.forEach(({ x }, i) => {
      if (i % stride !== 0 && i !== positions.length - 1) return;
      const slitY = centerY + x * positionScale;
      line(apertureX + 7, slitY, screenX, detectorY, color, 1, 0.20);
    });
    dot(screenX, detectorY, 8, color);
    label("θ", apertureX + 55, centerY - 9, INK, 14, 850);
    line(apertureX + 8, centerY, screenX, centerY, LINE, 1);
    label("Screen", screenX, screenBottom + 22, MUTED, 11, 700, "center");
  }
  function drawDiffractionPhasors() {
    const showSeparate = diffractionType() === "double" && controls.separateSlits.checked;
    panel(PHASOR, "Phasor chain", showSeparate ? "two partial sums" : "discrete contributions");
    const { tagged } = diffractionPhasors();
    const values = tagged.map(({ z }) => z);
    const result = drawPhasorChain(values, PHASOR, currentColor());
    if (showSeparate) {
      const sum1 = csum(tagged.filter((item) => item.slit === 0).map((item) => item.z));
      const sum2 = csum(tagged.filter((item) => item.slit === 1).map((item) => item.z));
      const [x, y, w, h] = PHASOR;
      label(`|E₁| = ${fmt(cmag(sum1), 2)}`, x + 18, y + h - 33, ACCENT, 11, 800);
      label(`|E₂| = ${fmt(cmag(sum2), 2)}`, x + 112, y + h - 33, ACCENT_DARK, 11, 800);
      label(`|E| = ${fmt(cmag(result), 2)}`, x + w - 18, y + h - 33, RESULT, 11, 850, "right");
    }
  }
  function drawDiffractionGraph() {
    panel(GRAPH, "Fraunhofer diffraction", "I(θ) / I(0)");
    const [left, top, right, bottom] = chartAxes(
      GRAPH, "Observation angle θ", "Relative intensity", [[0, "0"], [0.5, "0.5"], [1, "1"]]
    );
    const points = [];
    for (let i = 0; i <= 500; i++) {
      const theta = -10 + 20 * i / 500;
      const intensity = diffractionIntensity(theta);
      points.push([left + i / 500 * (right - left), bottom - intensity * (bottom - top)]);
    }
    polyline(points, currentColor(), 3);
    for (const theta of [-10, -5, 0, 5, 10]) {
      const px = left + (theta + 10) / 20 * (right - left);
      label(`${theta < 0 ? "−" + Math.abs(theta) : theta}°`, px, bottom + 18, MUTED, 11, 600, "center");
    }
    const theta = value(controls.angle);
    const intensity = diffractionIntensity(theta);
    const px = left + (theta + 10) / 20 * (right - left);
    const py = bottom - intensity * (bottom - top);
    line(px, top, px, bottom, currentColor(), 1.2, 0.35);
    dot(px, py, 6, currentColor());
  }
  function drawDiffraction() {
    drawDiffractionGeometry();
    drawDiffractionPhasors();
    drawDiffractionGraph();
  }

  // -------------------------------------------------------------------------
  // Readouts, formulas and experiment navigation
  // -------------------------------------------------------------------------
  function setReadouts(labels, values) {
    for (let i = 0; i < 4; i++) {
      controls.readoutLabels[i].textContent = labels[i];
      controls.readoutValues[i].textContent = values[i];
    }
  }
  function updateReadouts() {
    if (state.experiment === "film") {
      const { deltaPhi, total, reflectance } = filmValues();
      setReadouts(
        ["Thickness d", "Phase difference", "Field amplitude |E|", "Reflectance R"],
        [
          `${Math.round(value(controls.thickness))} nm`,
          `${fmt(phaseMod(deltaPhi), 2)} rad`,
          fmt(cmag(total), 3),
          `${fmt(reflectance * 100, 1)}%`,
        ]
      );
    } else if (state.experiment === "mirror") {
      const { xs, values } = mirrorPhasors();
      const selected = state.hoverSegment === null ? "–" : `x = ${fmt(xs[state.hoverSegment], 2)} µm`;
      setReadouts(
        ["Contributions", "Mirror region", "Stationary point", "|E|²"],
        [
          String(xs.length),
          selected,
          `x = ${fmt(classicReflectionX(), 2)} µm`,
          fmt(cmag2(csum(values)), 3),
        ]
      );
    } else {
      const theta = value(controls.angle);
      const { tagged } = diffractionPhasors();
      const total = csum(tagged.map(({ z }) => z));
      setReadouts(
        ["Aperture type", "Angle θ", "Field amplitude |E|", "Relative intensity"],
        [
          diffractionType() === "single" ? "Single slit" : "Double slit",
          `${fmt(theta, 2)}°`,
          fmt(cmag(total), 3),
          fmt(diffractionIntensity(theta), 3),
        ]
      );
    }
  }
  function formulaCard(title, formula, valueText = "") {
    const valueHtml = valueText ? `<p class="formula-value">${valueText}</p>` : "";
    return `<article class="formula-card"><h3>${title}</h3><code>${formula}</code>${valueHtml}</article>`;
  }
  function updateFormulaPanel() {
    if (state.experiment === "film") {
      const { deltaPhi, total, reflectance } = filmValues();
      controls.formulaTitle.textContent = "Thin Glass Film";
      controls.formulaNote.textContent = "Two equal-amplitude field contributions at normal incidence; no multiple reflections or Fresnel coefficients.";
      controls.formulaContent.innerHTML = [
        formulaCard("Optical path difference", "ΔL<sub>opt</sub> = 2nd",
          `2 × ${fmt(value(controls.refractiveIndex), 2)} × ${Math.round(value(controls.thickness))} nm`),
        formulaCard("Phase difference", "Δφ = 4πnd / λ + π",
          `Δφ mod 2π = ${fmt(phaseMod(deltaPhi), 2)} rad`),
        formulaCard("Phasor sum", "E = 0.2 + 0.2 e<sup>iΔφ</sup>",
          `|E| = ${fmt(cmag(total), 3)}`),
        formulaCard("Model reflectance", "R = |E|²",
          `R = ${fmt(reflectance * 100, 1)}%`),
      ].join("");
    } else if (state.experiment === "mirror") {
      const { xs, values } = mirrorPhasors();
      const result = csum(values);
      controls.formulaTitle.textContent = "Mirror";
      controls.formulaNote.textContent = "Equal-weight contributions from discrete mirror regions.";
      controls.formulaContent.innerHTML = [
        formulaCard("Path length", "L(x) = L<sub>Sx</sub> + L<sub>xD</sub>"),
        formulaCard("Relative phase", "φ(x) = 2π[L(x) − L<sub>ref</sub>] / λ"),
        formulaCard("Total field", "E = Σ A e<sup>iφ(x)</sup>",
          `N = ${xs.length}; |E| = ${fmt(cmag(result), 3)}`),
        formulaCard("Stationary phase", "dL/dx = 0 ⇒ α = β",
          `x<sub>stat</sub> = ${fmt(classicReflectionX(), 2)} µm`),
      ].join("");
    } else {
      const theta = value(controls.angle);
      const intensity = diffractionIntensity(theta);
      const double = diffractionType() === "double";
      controls.formulaTitle.textContent = "Fraunhofer Diffraction";
      controls.formulaNote.textContent = "Discrete phasor chain; analytic far-field intensity curve.";
      const intensityFormula = double
        ? "I / I(0) = (sin β / β)² · cos² α"
        : "I / I(0) = (sin β / β)²";
      const parameters = "β = πa sin θ / λ" + (double ? "; α = πd sin θ / λ" : "");
      controls.formulaContent.innerHTML = [
        formulaCard("Contribution phase", "φ(x) = kx sin θ"),
        formulaCard("Total field", "E(θ) ∝ ∫ e<sup>ikx sin θ</sup> dx"),
        formulaCard("Parameters", parameters, `θ = ${fmt(theta, 2)}°`),
        formulaCard("Intensity", intensityFormula, `I / I(0) = ${fmt(intensity, 3)}`),
      ].join("");
    }
  }
  function syncControls() {
    const lam = wavelengthNm();
    const { rgb, name } = wavelengthColor(lam);
    controls.wavelengthReadout.textContent = `${Math.round(lam)} nm`;
    controls.colorPreview.style.background = rgbString(rgb);
    controls.colorName.textContent = name;
    controls.thicknessReadout.textContent = `${Math.round(value(controls.thickness))} nm`;
    controls.indexReadout.textContent = fmt(value(controls.refractiveIndex), 2);
    controls.compareWavelengthReadout.textContent = `${Math.round(value(controls.compareWavelength))} nm`;
    controls.compareControls.classList.toggle("hidden", !controls.compare.checked);
    controls.segmentReadout.textContent = String(Math.round(value(controls.segments)));

    const slitWidth = value(controls.slitWidth);
    const double = diffractionType() === "double";
    if (double) {
      // Two physically distinct slits may not overlap.
      const minDistance = Math.min(60, slitWidth + 1);
      controls.slitDistance.min = String(minDistance);
      if (value(controls.slitDistance) < minDistance) controls.slitDistance.value = String(minDistance);
    }
    controls.slitWidthReadout.textContent = `${fmt(slitWidth, 1)} µm`;
    controls.slitDistanceReadout.textContent = `${fmt(value(controls.slitDistance), 1)} µm`;
    controls.angleReadout.textContent = `${fmt(value(controls.angle), 2)}°`;
    controls.slitSegmentsReadout.textContent = String(Math.round(value(controls.slitSegments)));
    controls.slitDistanceControls.classList.toggle("hidden", !double);
    controls.separateRow.classList.toggle("hidden", !double);
  }
  function draw() {
    syncControls();
    clearCanvas();
    if (state.experiment === "film") drawFilm();
    else if (state.experiment === "mirror") drawMirror();
    else drawDiffraction();
    updateReadouts();
    if (!controls.formulaPanel.classList.contains("hidden")) updateFormulaPanel();
  }

  const SCENE_HINTS = {
    film: "Adjust film thickness and refractive index.",
    mirror: "Drag the source or detector; explore the mirror regions.",
    diffraction: "Drag the observation point along the screen.",
  };
  function switchExperiment(experiment) {
    if (!Object.hasOwn(SCENE_HINTS, experiment)) return;
    state.experiment = experiment;
    state.hoverSegment = null;
    state.dragTarget = null;
    document.querySelectorAll(".experiment-tab").forEach((button) => {
      const active = button.dataset.experiment === experiment;
      button.classList.toggle("active", active);
      button.setAttribute("aria-selected", String(active));
      button.tabIndex = active ? 0 : -1;
    });
    document.querySelectorAll(".scene-controls").forEach((section) => {
      section.classList.add("hidden");
    });
    byId(`${experiment}-controls`).classList.remove("hidden");
    controls.hint.textContent = SCENE_HINTS[experiment];
    canvas.style.cursor = experiment === "film" ? "default" : "grab";
    draw();
  }

  // -------------------------------------------------------------------------
  // Pointer and control interactions (mouse, touch, and pen)
  // -------------------------------------------------------------------------
  function canvasPosition(event) {
    const rect = canvas.getBoundingClientRect();
    return [
      (event.clientX - rect.left) * WIDTH / rect.width,
      (event.clientY - rect.top) * HEIGHT / rect.height,
    ];
  }
  function pointDistance(a, b) { return Math.hypot(a[0] - b[0], a[1] - b[1]); }
  function pointerDown(event) {
    const [px, py] = canvasPosition(event);
    if (state.experiment === "mirror") {
      if (pointDistance([px, py], mirrorToCanvas(...state.source)) <= 18) {
        state.dragTarget = "source";
      } else if (pointDistance([px, py], mirrorToCanvas(...state.detector)) <= 18) {
        state.dragTarget = "detector";
      }
    } else if (state.experiment === "diffraction") {
      const [gx, gy, gw, gh] = GEOMETRY;
      if (px >= gx + gw - 105 && px <= gx + gw && py >= gy + 45 && py <= gy + gh - 25) {
        state.dragTarget = "screen";
      }
    }
    if (state.dragTarget) {
      canvas.setPointerCapture(event.pointerId);
      canvas.style.cursor = "grabbing";
      event.preventDefault();
    }
  }
  function pointerMove(event) {
    const [px, py] = canvasPosition(event);
    if (state.dragTarget === "source" || state.dragTarget === "detector") {
      state[state.dragTarget] = canvasToMirror(px, py);
      draw();
      return;
    }
    if (state.dragTarget === "screen") {
      const centerY = GEOMETRY[1] + GEOMETRY[3] / 2 + 8;
      const theta = clamp((centerY - py) / 12.2, -10, 10);
      controls.angle.value = fmt(theta, 2);
      draw();
      return;
    }
    if (state.experiment === "mirror") {
      const [gx, gy, gw, gh] = GEOMETRY;
      let nearest = null;
      if (px >= gx && px <= gx + gw && py >= gy + 45 && py <= gy + gh) {
        const [modelX] = canvasToMirror(px, py);
        const xs = mirrorSegments();
        let minDistance = Infinity;
        xs.forEach((x, i) => {
          const d = Math.abs(x - modelX);
          if (d < minDistance) { minDistance = d; nearest = i; }
        });
      }
      if (nearest !== state.hoverSegment) {
        state.hoverSegment = nearest;
        draw();
      }
    }
  }
  function pointerUp(event) {
    if (state.dragTarget !== null) {
      state.dragTarget = null;
      canvas.style.cursor = state.experiment === "film" ? "default" : "grab";
      try {
        if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
      } catch (_) { /* Pointer may already have been released by browser. */ }
    }
  }
  function pointerLeave() {
    if (state.experiment === "mirror" && state.dragTarget === null && state.hoverSegment !== null) {
      state.hoverSegment = null;
      draw();
    }
  }
  function toggleFormulas() {
    const opening = controls.formulaPanel.classList.contains("hidden");
    controls.formulaPanel.classList.toggle("hidden", !opening);
    controls.formulaToggle.textContent = opening ? "Hide formulas" : "Show formulas";
    controls.formulaToggle.setAttribute("aria-expanded", String(opening));
    if (opening) updateFormulaPanel();
  }

  function initialize() {
    document.querySelectorAll(".experiment-tab").forEach((button) => {
      button.addEventListener("click", () => switchExperiment(button.dataset.experiment));
      // Arrow-key navigation for tablist keyboard accessibility.
      button.addEventListener("keydown", (event) => {
        if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
        const tabs = Array.from(document.querySelectorAll(".experiment-tab"));
        const index = tabs.indexOf(button);
        const next = tabs[(index + (event.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
        switchExperiment(next.dataset.experiment);
        next.focus();
        event.preventDefault();
      });
    });
    [
      controls.wavelength, controls.thickness, controls.refractiveIndex,
      controls.compare, controls.compareWavelength, controls.segments,
      controls.classic, controls.pathGraph, controls.slitType,
      controls.slitWidth, controls.slitDistance, controls.angle,
      controls.slitSegments, controls.separateSlits,
    ].forEach((control) => control.addEventListener("input", draw));
    controls.formulaToggle.addEventListener("click", toggleFormulas);
    canvas.addEventListener("pointerdown", pointerDown);
    canvas.addEventListener("pointermove", pointerMove);
    canvas.addEventListener("pointerup", pointerUp);
    canvas.addEventListener("pointercancel", pointerUp);
    canvas.addEventListener("pointerleave", pointerLeave);
    switchExperiment("film");
    controls.status.classList.add("hidden");
  }

  try { initialize(); }
  catch (error) {
    console.error("Failed to initialize optical phasor applet:", error);
    controls.status.textContent = "Visualization could not be loaded. Check the browser console.";
    controls.status.classList.remove("hidden");
  }
})();
