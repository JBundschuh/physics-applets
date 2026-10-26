"use strict";

// Physics applet: particle motion and speed distribution.
// This is a two-dimensional, dimensionally simplified gas model.
// All particles have equal mass and radius; particle-particle and wall
// collisions are elastic. There is no friction or energy loss.

// 1. Canvas elements and controls.
const simCanvas = document.getElementById("sim-canvas");
const simCtx = simCanvas.getContext("2d");
const histCanvas = document.getElementById("hist-canvas");
const histCtx = histCanvas.getContext("2d");

const temperatureSlider = document.getElementById("temperature");
const temperatureValue = document.getElementById("temperature-value");
const particleCountSlider = document.getElementById("particle-count");
const particleCountValue = document.getElementById("particle-count-value");
const toggleButton = document.getElementById("toggle-button");
const resetButton = document.getElementById("reset-button");

// 2. Model parameters (screen units rather than a calibrated SI model).
const BASE_TEMPERATURE = 300.0;    // Reference temperature in kelvin.
const BASE_SIGMA = 85.0;           // Standard deviation of each velocity component at 300 K (px/s).
const PARTICLE_RADIUS = 4.0;      // Particle radius in canvas pixels.
const MAX_DT = 0.04;               // Maximum time step in seconds.
const PARTICLE_MASS = 1.0;        // Dimensionless model mass.

const COLLISIONS_ENABLED = true;
const COLLISION_ITERATIONS = 1;
const MIN_DISTANCE = 2.0 * PARTICLE_RADIUS;

// Fixed speed-to-color scale: raising the temperature typically makes
// more particles appear yellow or red.
const MAX_COLOR_TEMPERATURE = 1000.0;
const MAX_COLOR_SPEED_FACTOR = 3.0;

let temperature = Number(temperatureSlider.value);
let particleCount = Number(particleCountSlider.value);
let isRunning = true;
let previousTimestamp = null;

// 3. Simulation state: each particle stores x, y, vx, and vy.
let particles = [];

// 4. Model functions.
function sigmaFromTemperature(temp) {
  // Typical particle speeds are proportional to the square root of temperature.
  return BASE_SIGMA * Math.sqrt(temp / BASE_TEMPERATURE);
}

function gaussianRandom() {
  // Box-Muller transform: a standard normal random variable.
  // Equivalent in distribution to Python's random.gauss(0, 1).
  const u1 = Math.max(Number.MIN_VALUE, Math.random());
  const u2 = Math.random();
  return Math.sqrt(-2.0 * Math.log(u1)) * Math.cos(2.0 * Math.PI * u2);
}

function randomVelocity(temp) {
  // Two independent Gaussian velocity components produce a Rayleigh
  // distribution of speed magnitudes in two dimensions.
  const sigma = sigmaFromTemperature(temp);
  return { vx: sigma * gaussianRandom(), vy: sigma * gaussianRandom() };
}

function initializeParticles() {
  // Initialize all particles on startup, after reset, or when N changes.
  particles = [];
  for (let i = 0; i < particleCount; i += 1) {
    const velocity = randomVelocity(temperature);
    particles.push({
      x: PARTICLE_RADIUS + Math.random() * (simCanvas.width - 2 * PARTICLE_RADIUS),
      y: PARTICLE_RADIUS + Math.random() * (simCanvas.height - 2 * PARTICLE_RADIUS),
      vx: velocity.vx,
      vy: velocity.vy,
    });
  }
}

function scaleVelocities(oldTemperature, newTemperature) {
  // Adjust the existing speeds when the temperature slider changes.
  if (oldTemperature <= 0) return;
  const factor = Math.sqrt(newTemperature / oldTemperature);
  for (const particle of particles) {
    particle.vx *= factor;
    particle.vy *= factor;
  }
}

function particleSpeeds() {
  return particles.map((particle) => Math.hypot(particle.vx, particle.vy));
}

function meanSpeed() {
  const speeds = particleSpeeds();
  if (speeds.length === 0) return 0.0;
  return speeds.reduce((sum, speed) => sum + speed, 0.0) / speeds.length;
}

function totalKineticEnergy() {
  // E_kin = sum(1/2 * m * v^2); the result has model energy units.
  let energy = 0.0;
  for (const particle of particles) {
    energy += 0.5 * PARTICLE_MASS * (particle.vx ** 2 + particle.vy ** 2);
  }
  return energy;
}

function theoretical2DSpeedDistribution(speed, temp) {
  // Rayleigh distribution, i.e., the speed distribution associated with
  // two independent, normally distributed velocity components.
  const sigma = sigmaFromTemperature(temp);
  if (sigma <= 0) return 0.0;
  return speed / (sigma ** 2) * Math.exp(-(speed ** 2) / (2.0 * sigma ** 2));
}

// 5. Time evolution and elastic collisions.
function handleElasticCollision(p1, p2) {
  // Two particles have identical mass and radius.
  // The velocity component along the collision normal is exchanged.
  const dx = p2.x - p1.x;
  const dy = p2.y - p1.y;
  const distanceSquared = dx * dx + dy * dy;

  let distance;
  let nx;
  let ny;
  if (distanceSquared === 0) {
    // Choose a random collision normal if positions coincide exactly.
    const angle = 2.0 * Math.PI * Math.random();
    nx = Math.cos(angle);
    ny = Math.sin(angle);
    distance = 0.0;
  } else {
    distance = Math.sqrt(distanceSquared);
    nx = dx / distance;
    ny = dy / distance;
  }

  const overlap = MIN_DISTANCE - distance;
  if (overlap <= 0) return;

  // Resolve overlap symmetrically, preserving the original collision logic.
  const correction = 0.5 * overlap;
  p1.x -= correction * nx;
  p1.y -= correction * ny;
  p2.x += correction * nx;
  p2.y += correction * ny;

  const relativeNormalSpeed = (p1.vx - p2.vx) * nx + (p1.vy - p2.vy) * ny;
  if (relativeNormalSpeed <= 0) return; // The particles are moving apart.

  const impulse = relativeNormalSpeed;
  p1.vx -= impulse * nx;
  p1.vy -= impulse * ny;
  p2.vx += impulse * nx;
  p2.vy += impulse * ny;
}

function handleParticleCollisions() {
  // Check each particle pair (O(N^2)), as in the Python implementation.
  if (!COLLISIONS_ENABLED) return;
  for (let iteration = 0; iteration < COLLISION_ITERATIONS; iteration += 1) {
    for (let i = 0; i < particles.length; i += 1) {
      for (let j = i + 1; j < particles.length; j += 1) {
        handleElasticCollision(particles[i], particles[j]);
      }
    }
  }
}

function updateModel(dt) {
  const width = simCanvas.width;
  const height = simCanvas.height;

  // Free motion and elastic reflection at the box walls.
  for (const particle of particles) {
    particle.x += particle.vx * dt;
    particle.y += particle.vy * dt;

    if (particle.x < PARTICLE_RADIUS) {
      particle.x = PARTICLE_RADIUS;
      particle.vx *= -1;
    } else if (particle.x > width - PARTICLE_RADIUS) {
      particle.x = width - PARTICLE_RADIUS;
      particle.vx *= -1;
    }

    if (particle.y < PARTICLE_RADIUS) {
      particle.y = PARTICLE_RADIUS;
      particle.vy *= -1;
    } else if (particle.y > height - PARTICLE_RADIUS) {
      particle.y = height - PARTICLE_RADIUS;
      particle.vy *= -1;
    }
  }

  handleParticleCollisions();
}

// 6. Drawing helpers and color scale.
function clamp(value, minimum, maximum) {
  return Math.max(minimum, Math.min(maximum, value));
}

function mixColors(colorA, colorB, share) {
  const t = clamp(share, 0.0, 1.0);
  const r = Math.trunc(colorA[0] + t * (colorB[0] - colorA[0]));
  const g = Math.trunc(colorA[1] + t * (colorB[1] - colorA[1]));
  const b = Math.trunc(colorA[2] + t * (colorB[2] - colorA[2]));
  return `rgb(${r}, ${g}, ${b})`;
}

function colorFromSpeed(speed) {
  // Absolute color mapping: blue -> cyan -> yellow -> red.
  const maxSpeed = MAX_COLOR_SPEED_FACTOR * sigmaFromTemperature(MAX_COLOR_TEMPERATURE);
  if (maxSpeed <= 0) return "rgb(37, 99, 235)";
  const s = clamp(speed / maxSpeed, 0.0, 1.0);

  const blue = [37, 99, 235];
  const cyan = [34, 211, 238];
  const yellow = [250, 204, 21];
  const red = [220, 38, 38];

  if (s < 1 / 3) return mixColors(blue, cyan, 3 * s);
  if (s < 2 / 3) return mixColors(cyan, yellow, 3 * (s - 1 / 3));
  return mixColors(yellow, red, 3 * (s - 2 / 3));
}

function drawSimulation() {
  const width = simCanvas.width;
  const height = simCanvas.height;
  simCtx.clearRect(0, 0, width, height);
  simCtx.fillStyle = "#f9fafb";
  simCtx.fillRect(0, 0, width, height);

  for (const particle of particles) {
    const speed = Math.hypot(particle.vx, particle.vy);
    simCtx.fillStyle = colorFromSpeed(speed);
    simCtx.beginPath();
    simCtx.arc(particle.x, particle.y, PARTICLE_RADIUS, 0, 2 * Math.PI);
    simCtx.fill();
    simCtx.strokeStyle = "rgba(17, 24, 39, 0.25)";
    simCtx.lineWidth = 0.8;
    simCtx.stroke();
  }

  simCtx.fillStyle = "#111827";
  simCtx.font = "15px system-ui";
  simCtx.fillText(`T = ${Math.trunc(temperature)} K, N = ${particleCount}`, 14, 24);
}

function drawMeasurementsInHistogram(left, top, plotWidth) {
  const averageSpeed = meanSpeed();
  const kineticEnergy = totalKineticEnergy();
  const boxWidth = 190;
  const boxHeight = 54;
  const x = left + plotWidth - boxWidth - 8;
  const y = top + 8;

  histCtx.fillStyle = "rgba(255, 255, 255, 0.88)";
  histCtx.fillRect(x, y, boxWidth, boxHeight);
  histCtx.strokeStyle = "rgba(55, 65, 81, 0.35)";
  histCtx.lineWidth = 1.0;
  histCtx.strokeRect(x, y, boxWidth, boxHeight);

  histCtx.fillStyle = "#111827";
  histCtx.font = "13px system-ui";
  histCtx.fillText(`<v> = ${averageSpeed.toFixed(1)} px/s`, x + 10, y + 22);
  histCtx.fillText(`E_kin = ${kineticEnergy.toFixed(0)}`, x + 10, y + 42);
}

function drawHistogram() {
  // Normalized speed histogram and theoretical 2D Rayleigh distribution.
  const width = histCanvas.width;
  const height = histCanvas.height;
  histCtx.clearRect(0, 0, width, height);
  histCtx.fillStyle = "#ffffff";
  histCtx.fillRect(0, 0, width, height);

  const left = 60;
  const right = 20;
  const top = 25;
  const bottom = 45;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;

  const speeds = particleSpeeds();
  if (speeds.length === 0) return;

  const sigma = sigmaFromTemperature(temperature);
  const maxSpeed = Math.max(...speeds, 4.5 * sigma);
  const binCount = 22;
  const binWidth = maxSpeed / binCount;
  const bins = new Array(binCount).fill(0);

  for (const speed of speeds) {
    const index = Math.min(Math.trunc(speed / binWidth), binCount - 1);
    bins[index] += 1;
  }
  // Density, not absolute frequency, to make the comparison meaningful.
  const densities = bins.map((count) => count / (speeds.length * binWidth));

  const curve = [];
  for (let i = 0; i < 180; i += 1) {
    const speed = maxSpeed * i / 179;
    curve.push([speed, theoretical2DSpeedDistribution(speed, temperature)]);
  }
  const maxY = Math.max(...densities, ...curve.map((point) => point[1]), Number.MIN_VALUE);

  const xCanvas = (speed) => left + (speed / maxSpeed) * plotWidth;
  const yCanvas = (density) => top + plotHeight - (density / maxY) * plotHeight;

  // Axes.
  histCtx.strokeStyle = "#374151";
  histCtx.lineWidth = 1.0;
  histCtx.beginPath();
  histCtx.moveTo(left, top);
  histCtx.lineTo(left, top + plotHeight);
  histCtx.lineTo(left + plotWidth, top + plotHeight);
  histCtx.stroke();

  // Colored histogram bars.
  for (let i = 0; i < densities.length; i += 1) {
    const speedLeft = i * binWidth;
    const speedRight = (i + 1) * binWidth;
    const speedMid = 0.5 * (speedLeft + speedRight);
    const x0 = xCanvas(speedLeft);
    const x1 = xCanvas(speedRight);
    const y = yCanvas(densities[i]);
    const barWidth = Math.max(1, x1 - x0 - 2);
    const barHeight = top + plotHeight - y;

    histCtx.fillStyle = colorFromSpeed(speedMid);
    histCtx.fillRect(x0 + 1, y, barWidth, barHeight);
    histCtx.strokeStyle = "rgba(17, 24, 39, 0.18)";
    histCtx.lineWidth = 0.6;
    histCtx.strokeRect(x0 + 1, y, barWidth, barHeight);
  }

  // Theoretical distribution curve.
  histCtx.strokeStyle = "#dc2626";
  histCtx.lineWidth = 2.5;
  histCtx.beginPath();
  for (let i = 0; i < curve.length; i += 1) {
    const [speed, density] = curve[i];
    if (i === 0) histCtx.moveTo(xCanvas(speed), yCanvas(density));
    else histCtx.lineTo(xCanvas(speed), yCanvas(density));
  }
  histCtx.stroke();

  // Axes, legend, and numeric labels.
  histCtx.fillStyle = "#111827";
  histCtx.font = "14px system-ui";
  histCtx.fillText("Speed v / px s⁻¹", left + plotWidth / 2 - 70, height - 12);
  histCtx.fillText("Density", 10, top + 12);
  histCtx.font = "13px system-ui";
  histCtx.fillText("Histogram (color = speed)", left + 12, top + 18);
  histCtx.fillStyle = "#dc2626";
  histCtx.fillText("Theory", left + 250, top + 18);
  histCtx.fillStyle = "#374151";
  histCtx.fillText("0", left - 4, top + plotHeight + 20);
  histCtx.fillText(String(Math.trunc(maxSpeed)), left + plotWidth - 25, top + plotHeight + 20);

  drawMeasurementsInHistogram(left, top, plotWidth);
}

function drawAll() {
  drawSimulation();
  drawHistogram();
}

// 7. User interaction.
temperatureSlider.addEventListener("input", () => {
  const previousTemperature = temperature;
  temperature = Number(temperatureSlider.value);
  scaleVelocities(previousTemperature, temperature);
  temperatureValue.textContent = String(Math.trunc(temperature));
  drawAll();
});

particleCountSlider.addEventListener("input", () => {
  particleCount = Number(particleCountSlider.value);
  particleCountValue.textContent = String(particleCount);
  initializeParticles();
  drawAll();
});

toggleButton.addEventListener("click", () => {
  isRunning = !isRunning;
  toggleButton.textContent = isRunning ? "Pause" : "Start";
});

resetButton.addEventListener("click", () => {
  initializeParticles();
  drawAll();
});

// 8. Browser animation loop.
function animationFrame(timestamp) {
  if (previousTimestamp === null) previousTimestamp = timestamp;
  let dt = (timestamp - previousTimestamp) / 1000.0;
  previousTimestamp = timestamp;
  dt = Math.min(dt, MAX_DT);

  if (isRunning) updateModel(dt);
  drawAll();
  window.requestAnimationFrame(animationFrame);
}

initializeParticles();
drawAll();
window.requestAnimationFrame(animationFrame);
