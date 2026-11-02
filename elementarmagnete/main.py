"""
Elementarmagnete – Weiss-Bezirke und Magnetisierung
=================================================

Dateien: index.html, style.css, main.py (gemeinsam über HTTP bereitstellen).
Laufzeit: PyScript / Pyodide mit NumPy; keine serverseitige Python-Anwendung.

Didaktischer Umfang
------------------
* Ferromagnet: vorbereiteter Mehrbezirkszustand oder magnetisierter Zustand.
* Idealisiertes paramagnetisches Vergleichsmaterial.
* Beweglicher äußerer Stabmagnet, Polwechsel, Entfernen, Temperatur.
* Feldpfeile, resultierende Magnetisierung und optionale Nachbarkopplung.
* Keine Diamagneten, Antiferromagneten oder mechanischen Schläge.

Modell und Grenzen
------------------
Feste Gitterplätze, planare Einheitsvektoren s_i = (cos(theta_i), sin(theta_i)).
Ein Symbol ist ein repräsentatives magnetisches Moment, KEIN ganzer Bezirk.
Das diskrete klassische Modell ist keine quantenmechanische Simulation.

E = -J sum_<ij> s_i.s_j - sum_i K_i (s_i.e_x)^2
    - 1/2 sum_i s_i.B_dip,i - sum_i s_i.B_ext,i

J, K und alle Felder sind konsistent in reduzierten Energieeinheiten angegeben.
Die Temperatur ist k_B T / E_ref; E_ref bleibt bei Änderung von J konstant.
Die Dipolnäherung verwendet das räumliche 1/r^3-Gesetz, ausgewertet in der Ebene.
Keine periodischen Ränder, keine Selbstwechselwirkung, keine Feldabschneidung
am Materialrand. Die Magnetgeometrie bleibt unverändert.

Relaxation (Mobilität = 1 in Modellzeit):
d theta_i = -(dE/d theta_i) dt + sqrt(2 T dt) N(0, 1).
Keine Präzession und keine Vorhersage realer Relaxationszeiten oder Curie-Werte.
Materialunregelmäßigkeiten sind ortsfest; thermisches Rauschen ist zeitabhängig.
Remanenz entsteht aus dem Modell, nicht durch Einfrieren magnetisierter Pfeile.

Grundlagen:
https://fidimag.readthedocs.io/en/latest/physics_num_methods/core_eqs.html
https://math.nist.gov/oommf/doc/userguide21a0/userguidexml/sec_oxsEnergies.html
https://docs.pyscript.net/2026.7.2/

Der Modellkern kann für numerische Prüfungen auch in normalem Python importiert
werden. Erst der letzte Abschnitt startet die Browseranwendung.
"""

import asyncio
import math
import time
import traceback

import numpy as np

try:
    from js import document, window
    from pyodide.ffi import create_proxy
    IN_BROWSER = True
except ImportError:
    IN_BROWSER = False


# -----------------------------------------------------------------------------
# 1. Modell und Darstellung
# -----------------------------------------------------------------------------

COLS, ROWS = 24, 16
DEFAULT_SEED = 7319
MODEL_DT = 0.012
MODEL_TIME_PER_SECOND = 1.8
MAX_STEPS_PER_FRAME = 12

DEFAULT_T = 0.08
DIPOLAR_STRENGTH = 0.32

MATERIAL_PRESETS = {
    "soft": {
        "material": "ferro",
        "j": 0.85,
        "anisotropy": 0.05,
        "pinning": 0.10,
    },
    "hard": {
        "material": "ferro",
        "j": 0.85,
        "anisotropy": 0.15,
        "pinning": 0.70,
    },
    "para": {
        "material": "para",
        "j": 0.0,
        "anisotropy": 0.0,
        "pinning": 0.0,
    },
}

W, H = 1120, 560
CELL = 22.0
PROBE_X, PROBE_Y = 500.0, 104.0
PROBE_W, PROBE_H = COLS * CELL, ROWS * CELL
PROBE_CX = PROBE_X + PROBE_W / 2
PROBE_CY = PROBE_Y + PROBE_H / 2

MAGNET_W, MAGNET_H = 156.0, 52.0
MAGNET_MOMENT = 750.0
SOURCE_CORE = 1.15  # in Gitterabständen; nur für den äußeren Stabmagneten
PARK_X, PARK_Y = 175.0, PROBE_CY

INK = "#1e293b"
MUTED = "#64748b"
NORTH = "#ca4c49"
SOUTH = "#2f8f5b"
FIELD_COLOR = "#708795"


# -----------------------------------------------------------------------------
# 2. Reiner Modellkern
# -----------------------------------------------------------------------------

class MagneticModel:
    """Diskretes planares Spinmodell mit offenen Rändern und festen Defekten."""

    def __init__(self, cols=COLS, rows=ROWS, seed=DEFAULT_SEED):
        self.cols, self.rows = int(cols), int(rows)
        self.n = self.cols * self.rows
        self.seed = int(seed)

        xx, yy = np.meshgrid(
            np.arange(self.cols) - (self.cols - 1) / 2,
            np.arange(self.rows) - (self.rows - 1) / 2,
        )
        self.positions = np.column_stack((xx.ravel(), yy.ravel()))

        ids = np.arange(self.n).reshape(self.rows, self.cols)
        self.pair_a = np.concatenate((ids[:, :-1].ravel(), ids[:-1, :].ravel()))
        self.pair_b = np.concatenate((ids[:, 1:].ravel(), ids[1:, :].ravel()))

        self.tensor = self.dipole_kernel(self.positions, self.positions, self_field=True)
        self.temperature = DEFAULT_T
        self.apply_preset("soft")
        self.theta = np.zeros(self.n)
        self.rng = np.random.default_rng(self.seed)
        self.elapsed = 0.0
        self.initialise("domains")

    @staticmethod
    def dipole_kernel(targets, sources, self_field=False):
        """Geometrischer 2D-Schnitt des üblichen 3D-Dipolfeldtensors."""
        targets = np.asarray(targets, dtype=float)
        sources = np.asarray(sources, dtype=float)
        delta = targets[:, None, :] - sources[None, :, :]
        r2 = np.sum(delta * delta, axis=2)
        if self_field:
            np.fill_diagonal(r2, np.inf)
        elif np.any(r2 < 1e-12):
            raise ValueError("Feldpunkt darf nicht auf einer idealen Dipolquelle liegen.")

        inv3 = r2 ** -1.5
        inv5 = r2 ** -2.5
        dx, dy = delta[:, :, 0], delta[:, :, 1]
        return (
            3 * dx * dx * inv5 - inv3,
            3 * dx * dy * inv5,
            3 * dy * dy * inv5 - inv3,
        )

    def apply_preset(self, name):
        if name not in MATERIAL_PRESETS:
            raise ValueError(f"Unbekanntes Materialpreset: {name}")
    
        preset = MATERIAL_PRESETS[name]
        self.preset = name
        self.material = preset["material"]
        self.j = preset["j"]
        self.anisotropy = preset["anisotropy"]
        self.pinning = preset["pinning"]
        self.k = self._make_anisotropy()

    def _make_anisotropy(self):
        """Gleiche Pinningpositionen, materialabhängige Stärke."""
        x = self.positions[:, 0] / self.cols
        y = self.positions[:, 1] / self.rows
        profile = np.ones(self.n)
    
        for cx, cy in (
            (0.0, 0.0),
            (-0.28, 0.0),
            (0.28, 0.0),
            (-0.18, 0.28),
            (0.18, -0.28),
            (0.18, 0.28),
            (-0.18, -0.28),
        ):
            profile -= self.pinning * np.exp(
                -((x - cx) ** 2 / 0.011 + (y - cy) ** 2 / 0.009)
            )
    
        return self.anisotropy * np.maximum(profile, 0.10)

    def initialise(self, initial="domains"):
        self.elapsed = 0.0
        self.rng = np.random.default_rng(self.seed)
        if self.material == "para":
            self.theta = self.rng.uniform(-math.pi, math.pi, self.n)
        elif initial == "magnetized":
            self.theta = np.zeros(self.n)
        else:
            x, y = self.positions.T
            self.theta = np.arctan2(y, x) + math.pi / 2
        self.wrap_angles()

    def wrap_angles(self):
        self.theta = (self.theta + math.pi) % (2 * math.pi) - math.pi

    def spins(self):
        return np.column_stack((np.cos(self.theta), np.sin(self.theta)))

    def dipole_field(self, spins=None):
        spins = self.spins() if spins is None else spins
        if self.material == "para":
            return np.zeros_like(spins)
        dxx, dxy, dyy = self.tensor
        sx, sy = spins.T
        return DIPOLAR_STRENGTH * np.column_stack((
            dxx @ sx + dxy @ sy,
            dxy @ sx + dyy @ sy,
        ))

    def effective_field(self, external):
        spins = self.spins()
        field = np.array(external, dtype=float, copy=True)

        if self.material == "ferro":
            grid = spins.reshape(self.rows, self.cols, 2)
            neighbours = np.zeros_like(grid)
            neighbours[:, :-1] += grid[:, 1:]
            neighbours[:, 1:] += grid[:, :-1]
            neighbours[:-1] += grid[1:]
            neighbours[1:] += grid[:-1]
            field += self.j * neighbours.reshape(self.n, 2)
            field[:, 0] += 2 * self.k * spins[:, 0]
            field += self.dipole_field(spins)

        return spins, field

    def torque(self, external):
        spins, field = self.effective_field(external)
        return spins[:, 0] * field[:, 1] - spins[:, 1] * field[:, 0]

    def step(self, external, dt=MODEL_DT, temperature=None):
        """Euler-Maruyama für überdämpfte Winkelrelaxation."""
        temp = self.temperature if temperature is None else float(temperature)
        if dt <= 0 or temp < 0:
            raise ValueError("dt muss positiv und die Temperatur nichtnegativ sein.")

        max_external = float(np.max(np.linalg.norm(external, axis=1)))
        stiffness = max_external + 8 * self.j + 4 * self.anisotropy + 8
        parts = max(1, int(math.ceil(dt * stiffness / 0.3)))
        h = dt / parts

        for _ in range(parts):
            self.theta += h * self.torque(external)
            if temp > 0:
                self.theta += math.sqrt(2 * temp * h) * self.rng.normal(size=self.n)
            self.wrap_angles()

        self.elapsed += dt

    def energy_terms(self, external):
        spins = self.spins()
        ferro = self.material == "ferro"
        return {
            "exchange": -self.j * float(np.sum(spins[self.pair_a] * spins[self.pair_b])) if ferro else 0.0,
            "anisotropy": -float(np.sum(self.k * spins[:, 0] ** 2)) if ferro else 0.0,
            "dipolar": -0.5 * float(np.sum(spins * self.dipole_field(spins))) if ferro else 0.0,
            "external": -float(np.sum(spins * external)),
        }

    def observables(self):
        spins = self.spins()
        mean = np.mean(spins, axis=0)
        return mean, float(np.linalg.norm(mean))


# -----------------------------------------------------------------------------
# 3. Äußerer Stabmagnet
# -----------------------------------------------------------------------------

def canvas_to_world(points):
    result = np.array(points, dtype=float, copy=True)
    result[..., 0] = (result[..., 0] - PROBE_CX) / CELL
    result[..., 1] = (PROBE_CY - result[..., 1]) / CELL
    return result


def softened_dipole_kernel(targets, sources, core_radius=SOURCE_CORE):
    """Dipoltensor mit endlichem Kernradius für die sichtbare Feldquelle.

    Fern vom Magneten geht die Form in das übliche 1/r^3-Dipolfeld über.
    Der Kern vermeidet die Singularität, wenn der Magnet über der Probe liegt.
    """
    targets = np.asarray(targets, dtype=float)
    sources = np.asarray(sources, dtype=float)
    delta = targets[:, None, :] - sources[None, :, :]
    r2 = np.sum(delta * delta, axis=2) + float(core_radius) ** 2
    inv3 = r2 ** -1.5
    inv5 = r2 ** -2.5
    dx, dy = delta[:, :, 0], delta[:, :, 1]
    return (
        3 * dx * dx * inv5 - inv3,
        3 * dx * dy * inv5,
        3 * dy * dy * inv5 - inv3,
    )


def source_field(points, magnet_x, magnet_y, polarity=1, enabled=True,):
    if not enabled:
        return np.zeros((len(points), 2))

    offsets = np.linspace(-MAGNET_W * 0.37, MAGNET_W * 0.37, 7)
    sources_px = np.column_stack((magnet_x + offsets, np.full(7, magnet_y)))
    sources = canvas_to_world(sources_px)
    dxx, dxy, _ = softened_dipole_kernel(np.asarray(points), sources)
    moments = np.full(7, polarity * MAGNET_MOMENT / 7)
    return np.column_stack((dxx @ moments, dxy @ moments))


def constrain_magnet(x, y):
    """Der Magnet darf überall im Canvas liegen, auch über der Probe."""
    xmin, xmax = MAGNET_W / 2 + 18, W - MAGNET_W / 2 - 18
    ymin, ymax = MAGNET_H / 2 + 18, H - MAGNET_H / 2 - 18
    return float(min(xmax, max(xmin, x))), float(min(ymax, max(ymin, y)))


# -----------------------------------------------------------------------------
# 4. Browseranwendung
# -----------------------------------------------------------------------------

class MagnetApplet:
    def __init__(self):
        ids = (
            "simulation-canvas", "experiment-controls", "material", "initial-state",
            "temperature", "temperature-value", "show-field", "toggle-magnet", "flip-poles",
            "start-pause", "reset", "run-dot", "run-label", "material-badge",
            "magnetization-value", "magnetization-meter", "loading-panel",
            "loading-title", "loading-details",
        )
        self.nodes = {key: document.getElementById(key) for key in ids}
        missing = [key for key, node in self.nodes.items() if node is None]
        if missing:
            raise RuntimeError("Fehlende HTML-Elemente: " + ", ".join(missing))

        self.canvas = self.nodes["simulation-canvas"]
        self.ctx = self.canvas.getContext("2d")
        if self.ctx is None:
            raise RuntimeError("Der Browser stellt keinen 2D-Canvas bereit.")

        self.model = MagneticModel()
        self.proxies = []
        self.busy = True
        self.failed = False
        self.running = not bool(window.matchMedia("(prefers-reduced-motion: reduce)").matches)

        self.magnet_x, self.magnet_y = PARK_X, PARK_Y
        self.magnet_enabled = False
        self.polarity = 1
        self.drag_pointer = None
        self.drag_offset = (0.0, 0.0)
        self.show_field = True
        self.field_dirty = True
        self.external = np.zeros((self.model.n, 2))

        self.last_timestamp = None
        self.accumulator = 0.0
        self.last_draw = -1000.0
        self.last_field_draw = -1000.0
        self.cached_field = []
        self.pixel_ratio = 0.0
        self.raf_id = None
        self.display_values = {}

        self.palette = [f"hsla({i * 15}, 42%, 67%, 0.22)" for i in range(24)]
        self.centers = np.column_stack((
            PROBE_CX + CELL * self.model.positions[:, 0],
            PROBE_CY - CELL * self.model.positions[:, 1],
        )).tolist()

        gx, gy = np.meshgrid(np.arange(28, W - 18, 42), np.arange(62, H - 24, 42))
        self.field_pixels = np.column_stack((gx.ravel(), gy.ravel()))
        self.field_world = canvas_to_world(self.field_pixels)

        self._install_events()
        self.animation_proxy = create_proxy(self.animation_frame)
        self.proxies.append(self.animation_proxy)

    def text(self, key, value):
        value = str(value)
        if self.display_values.get(key) != value:
            self.nodes[key].textContent = value
            self.display_values[key] = value

    @staticmethod
    def decimal(value, digits=2):
        value = 0.0 if abs(value) < 0.5 * 10 ** (-digits) else float(value)
        return format(value, f".{digits}f").replace(".", ",")

    def listen(self, target, event, callback):
        proxy = create_proxy(callback)
        self.proxies.append(proxy)
        target.addEventListener(event, proxy)

    def _install_events(self):
        for key in ("material", "initial-state"):
            self.listen(self.nodes[key], "change", self.request_reset)
        self.listen(self.nodes["reset"], "click", self.request_reset)
        self.listen(self.nodes["start-pause"], "click", self.toggle_running)
        self.listen(self.nodes["toggle-magnet"], "click", self.toggle_magnet)
        self.listen(self.nodes["temperature"], "input", self.on_temperature)
        self.listen(self.nodes["show-field"], "change", self.on_display)
        self.listen(self.canvas, "pointerdown", self.on_pointer_down)
        self.listen(self.canvas, "pointermove", self.on_pointer_move)
        self.listen(self.canvas, "pointerup", self.on_pointer_end)
        self.listen(self.canvas, "pointercancel", self.on_pointer_end)
        self.listen(self.canvas, "lostpointercapture", self.on_pointer_end)
        self.listen(document, "visibilitychange", self.on_visibility)
        self.listen(self.nodes["flip-poles"], "click", self.flip_poles)

    async def start(self):
        await self.reset_experiment()
        if not self.failed:
            window.magnetAppletReady = True
            self.raf_id = window.requestAnimationFrame(self.animation_proxy)

    async def reset_experiment(self):
        if self.failed:
            return

        self.busy = True
        self.nodes["experiment-controls"].disabled = True
        self.nodes["loading-panel"].hidden = False
        self.text("loading-title", "Ausgangszustand wird vorbereitet …")
        self.text("loading-details", "")

        try:
            self.model.apply_preset(str(self.nodes["material"].value))
            self.model.temperature = DEFAULT_T
            self.nodes["temperature"].value = str(DEFAULT_T)
            self.nodes["show-field"].checked = True
            self.show_field = True

            self.magnet_x, self.magnet_y = PARK_X, PARK_Y
            self.magnet_enabled = False
            self.polarity = 1
            self.drag_pointer = None
            self.canvas.style.cursor = "default"
            self.external.fill(0)

            self.model.initialise(str(self.nodes["initial-state"].value))
            if self.model.material == "ferro":
                for _ in range(20):
                    for _ in range(35):
                        self.model.step(self.external, temperature=0.0)
                    await asyncio.sleep(0)

            self.model.elapsed = 0.0
            self.model.rng = np.random.default_rng(self.model.seed)
            self.field_dirty = True
            self.cached_field = []
            self.last_timestamp = None
            self.accumulator = 0.0
            self.last_field_draw = -1000.0
            self.busy = False

            self.nodes["loading-panel"].hidden = True
            self.nodes["experiment-controls"].disabled = False
            self.update_controls()
            self.draw(time.perf_counter())
        except Exception:
            self.report_error()

    def request_reset(self, _event=None):
        if self.busy or self.failed:
            return
        self.busy = True
        asyncio.create_task(self.reset_experiment())

    def update_controls(self):
        para = self.model.material == "para"
    
        labels = {
            "soft": "Weichferromagnetisch",
            "hard": "Hartferromagnetisch",
            "para": "Paramagnetisch",
        }
    
        self.nodes["initial-state"].disabled = para
        self.text("material-badge", labels[self.model.preset])
        self.text("temperature-value", self.decimal(self.model.temperature))
        self.text("start-pause", "Pause" if self.running else "Start")
        self.nodes["start-pause"].setAttribute(
            "aria-pressed", str(not self.running).lower()
        )
        self.text("run-label", "Simulation läuft" if self.running else "Pausiert")
        self.nodes["run-dot"].className = (
            "status-dot running" if self.running else "status-dot paused"
        )
        self.text(
            "toggle-magnet",
            "Magnet aus" if self.magnet_enabled else "Magnet an",
        )
        self.nodes["toggle-magnet"].setAttribute(
            "aria-pressed", str(self.magnet_enabled).lower()
        )
    
        self.nodes["flip-poles"].hidden = not self.magnet_enabled
        self.nodes["flip-poles"].disabled = not self.magnet_enabled

    def toggle_running(self, _event=None):
        if self.busy or self.failed:
            return
        self.running = not self.running
        self.accumulator = 0.0
        self.last_timestamp = None
        self.update_controls()

    def mark_field_changed(self):
        self.field_dirty = True
        self.last_field_draw = -1000.0
        self.update_controls()

    def toggle_magnet(self, _event=None):
        if not self.busy and not self.failed:
            self.magnet_enabled = not self.magnet_enabled
            self.mark_field_changed()

    def flip_poles(self, _event=None):
        if self.busy or self.failed or not self.magnet_enabled:
            return
    
        self.polarity *= -1
        self.mark_field_changed()

    def on_temperature(self, _event=None):
        self.model.temperature = float(self.nodes["temperature"].value)
        self.update_controls()

    def on_display(self, _event=None):
        self.show_field = bool(self.nodes["show-field"].checked)
        self.last_field_draw = -1000.0

    def event_point(self, event):
        rect = self.canvas.getBoundingClientRect()
        return (
            (float(event.clientX) - float(rect.left)) * W / float(rect.width),
            (float(event.clientY) - float(rect.top)) * H / float(rect.height),
        )

    def hit_magnet(self, x, y):
        return (
            self.magnet_enabled
            and abs(x - self.magnet_x) <= MAGNET_W / 2 + 14
            and abs(y - self.magnet_y) <= MAGNET_H / 2 + 14
        )

    def on_pointer_down(self, event):
        if self.busy or self.failed or self.drag_pointer is not None:
            return
        if str(event.pointerType) == "mouse" and int(event.button) != 0:
            return

        x, y = self.event_point(event)
        if self.hit_magnet(x, y):
            event.preventDefault()
            self.drag_pointer = int(event.pointerId)
            self.drag_offset = (self.magnet_x - x, self.magnet_y - y)
            self.canvas.setPointerCapture(self.drag_pointer)
            self.canvas.style.cursor = "grabbing"
            self.magnet_enabled = True
            self.mark_field_changed()

    def on_pointer_move(self, event):
        if self.busy or self.failed:
            return

        x, y = self.event_point(event)
        if self.drag_pointer is not None:
            if int(event.pointerId) != self.drag_pointer:
                return
            event.preventDefault()
            self.magnet_x, self.magnet_y = constrain_magnet(
                x + self.drag_offset[0], y + self.drag_offset[1]
            )
            self.mark_field_changed()
        else:
            self.canvas.style.cursor = "grab" if self.hit_magnet(x, y) else "default"

    def on_pointer_end(self, event):
        pointer = int(event.pointerId)
        if pointer == self.drag_pointer:
            self.drag_pointer = None
            if self.canvas.hasPointerCapture(pointer):
                self.canvas.releasePointerCapture(pointer)
            self.canvas.style.cursor = "grab"

    def on_visibility(self, _event=None):
        self.last_timestamp = None
        self.accumulator = 0.0

    # -------------------------------------------------------------------------
    # 5. Canvas
    # -------------------------------------------------------------------------

    def rounded_path(self, x, y, width, height, radius=10):
        ctx = self.ctx
        r = min(radius, width / 2, height / 2)
        ctx.beginPath()
        ctx.moveTo(x + r, y)
        ctx.lineTo(x + width - r, y)
        ctx.quadraticCurveTo(x + width, y, x + width, y + r)
        ctx.lineTo(x + width, y + height - r)
        ctx.quadraticCurveTo(x + width, y + height, x + width - r, y + height)
        ctx.lineTo(x + r, y + height)
        ctx.quadraticCurveTo(x, y + height, x, y + height - r)
        ctx.lineTo(x, y + r)
        ctx.quadraticCurveTo(x, y, x + r, y)
        ctx.closePath()

    def label(self, text, x, y, size=14, color=INK, weight=400, align="left"):
        ctx = self.ctx
        ctx.font = f"{weight} {size}px system-ui, sans-serif"
        ctx.fillStyle = color
        ctx.textAlign = align
        ctx.textBaseline = "middle"
        ctx.fillText(str(text), x, y)

    def refresh_field_view(self, now):
        if now - self.last_field_draw < 0.12:
            return
        self.last_field_draw = now

        if not self.show_field or not self.magnet_enabled:
            self.cached_field = []
            return

        points = self.field_pixels
        keep = (
            (np.abs(points[:, 0] - self.magnet_x) > MAGNET_W / 2 + 18)
            | (np.abs(points[:, 1] - self.magnet_y) > MAGNET_H / 2 + 18)
        )
        indexes = np.flatnonzero(keep)
        field = source_field(self.field_world[keep], self.magnet_x, self.magnet_y, polarity=self.polarity, enabled=True,)
        self.cached_field = [
            (float(points[i, 0]), float(points[i, 1]), bx, -by)
            for i, (bx, by) in zip(indexes.tolist(), field.tolist())
        ]

    def draw_background(self):
        ctx = self.ctx
        ctx.clearRect(0, 0, W, H)
        ctx.fillStyle = "#fcfcf8"
        ctx.fillRect(0, 0, W, H)

        ctx.fillStyle = "#e5ece8"
        for y in range(32, H, 30):
            for x in range(22, W, 30):
                ctx.fillRect(x, y, 1, 1)

        ctx.fillStyle = "#ffffff"
        self.rounded_path(PROBE_X - 3, PROBE_Y - 3, PROBE_W + 6, PROBE_H + 6, 10)
        ctx.fill()
        ctx.strokeStyle = "#b9cbc9"
        ctx.lineWidth = 1.4
        ctx.stroke()

    def draw_field(self):
        ctx = self.ctx
        ctx.strokeStyle = FIELD_COLOR
        ctx.lineWidth = 1.2
        ctx.globalAlpha = 0.52
        ctx.beginPath()

        for x, y, bx, by in self.cached_field:
            magnitude = math.hypot(bx, by)
            if magnitude < 0.004:
                continue
            length = 26 * (1 - math.exp(-magnitude / 0.6))
            if length < 1.5:
                continue

            ux, uy = bx / magnitude, by / magnitude
            x1, y1 = x - 0.5 * length * ux, y - 0.5 * length * uy
            x2, y2 = x + 0.5 * length * ux, y + 0.5 * length * uy
            head = min(5, length * 0.34)

            ctx.moveTo(x1, y1)
            ctx.lineTo(x2, y2)
            ctx.moveTo(x2 - head * ux + head * 0.48 * uy, y2 - head * uy - head * 0.48 * ux)
            ctx.lineTo(x2, y2)
            ctx.lineTo(x2 - head * ux - head * 0.48 * uy, y2 - head * uy + head * 0.48 * ux)

        ctx.stroke()
        ctx.globalAlpha = 1.0

    def draw_moments(self):
        ctx = self.ctx
        spins = self.model.spins().tolist()
        angles = self.model.theta.tolist()

        for (x, y), theta in zip(self.centers, angles):
            bucket = int(((theta + math.pi) / (2 * math.pi)) * 24) % 24
            ctx.fillStyle = self.palette[bucket]
            ctx.fillRect(x - CELL / 2 + 0.5, y - CELL / 2 + 0.5, CELL - 1, CELL - 1)

        ctx.lineWidth = 3.6
        ctx.lineCap = "round"
        for colour, start, end in ((SOUTH, -6.4, 0.0), (NORTH, 0.0, 6.4)):
            ctx.strokeStyle = colour
            ctx.beginPath()
            for (x, y), (sx, sy) in zip(self.centers, spins):
                ctx.moveTo(x + start * sx, y - start * sy)
                ctx.lineTo(x + end * sx, y - end * sy)
            ctx.stroke()

        ctx.fillStyle = NORTH
        ctx.beginPath()
        for (x, y), (sx, sy) in zip(self.centers, spins):
            ctx.moveTo(x + 8.2 * sx, y - 8.2 * sy)
            ctx.lineTo(x + 3.7 * sx + 2.7 * sy, y - 3.7 * sy + 2.7 * sx)
            ctx.lineTo(x + 3.7 * sx - 2.7 * sy, y - 3.7 * sy - 2.7 * sx)
            ctx.closePath()
        ctx.fill()
        ctx.lineCap = "butt"

    def draw_magnet(self):
        if not self.magnet_enabled: # hier richtig?
            return
        
        ctx = self.ctx
        x, y = self.magnet_x - MAGNET_W / 2, self.magnet_y - MAGNET_H / 2

        ctx.save()

        if self.polarity == 1:
            left_colour, left_label = SOUTH, "S"
            right_colour, right_label = NORTH, "N"
        else:
            left_colour, left_label = NORTH, "N"
            right_colour, right_label = SOUTH, "S"
        
        self.rounded_path(x, y, MAGNET_W, MAGNET_H, 9)
        ctx.save()
        ctx.clip()
        
        ctx.fillStyle = left_colour
        ctx.fillRect(x, y, MAGNET_W / 2, MAGNET_H)
        
        ctx.fillStyle = right_colour
        ctx.fillRect(x + MAGNET_W / 2, y, MAGNET_W / 2, MAGNET_H)
        
        ctx.fillStyle = "rgba(255,255,255,.13)"
        ctx.fillRect(x, y, MAGNET_W, 7)
        ctx.restore()
        
        ctx.strokeStyle = "#516678"
        ctx.lineWidth = 1.2
        ctx.stroke()
        
        self.label(
            left_label,
            x + MAGNET_W * 0.25,
            self.magnet_y,
            21,
            "white",
            750,
            "center",
        )
        self.label(
            right_label,
            x + MAGNET_W * 0.75,
            self.magnet_y,
            21,
            "white",
            750,
            "center",
        )
        
        ctx.restore()

        # self.rounded_path(x, y, MAGNET_W, MAGNET_H, 9)
        # ctx.save()
        # ctx.clip()
        # ctx.fillStyle = SOUTH
        # ctx.fillRect(x, y, MAGNET_W / 2, MAGNET_H)
        # ctx.fillStyle = NORTH
        # ctx.fillRect(x + MAGNET_W / 2, y, MAGNET_W / 2, MAGNET_H)
        # ctx.fillStyle = "rgba(255,255,255,.13)"
        # ctx.fillRect(x, y, MAGNET_W, 7)
        # ctx.restore()

        # ctx.strokeStyle = "#516678"
        # ctx.lineWidth = 1.2
        # ctx.stroke()
        # self.label("S", x + MAGNET_W * 0.25, self.magnet_y, 21, "white", 750, "center")
        # self.label("N", x + MAGNET_W * 0.75, self.magnet_y, 21, "white", 750, "center")
        # ctx.restore()

    def draw(self, now):
        ratio = min(2.0, max(1.0, float(window.devicePixelRatio or 1)))
        if ratio != self.pixel_ratio:
            self.pixel_ratio = ratio
            self.canvas.width = int(W * ratio)
            self.canvas.height = int(H * ratio)

        self.ctx.setTransform(ratio, 0, 0, ratio, 0, 0)
        self.refresh_field_view(now)
        self.draw_background()
        self.draw_field()
        self.draw_moments()
        self.draw_magnet()  # bewusst zuletzt: der Magnet darf die Probe überlagern

    # -------------------------------------------------------------------------
    # 6. Anzeige und Hauptschleife
    # -------------------------------------------------------------------------

    # def update_readouts(self):
    #     _, magnitude = self.model.observables()
    #     self.text("magnetization-value", f"{round(magnitude * 100)} %")
    #     self.nodes["magnetization-meter"].value = magnitude

    def animation_frame(self, timestamp):
        if self.failed:
            return

        try:
            stamp = float(timestamp) / 1000
            delta = 0 if self.last_timestamp is None else max(0.0, stamp - self.last_timestamp)
            self.last_timestamp = stamp

            if not self.busy and not bool(document.hidden):
                if self.field_dirty:
                    self.external = source_field(
                        self.model.positions, self.magnet_x, self.magnet_y, polarity=self.polarity, enabled=self.magnet_enabled,)
                    self.field_dirty = False

                if self.running:
                    self.accumulator += min(delta, 0.10) * MODEL_TIME_PER_SECOND
                    steps = 0
                    budget_start = time.perf_counter()
                    while self.accumulator >= MODEL_DT and steps < MAX_STEPS_PER_FRAME:
                        self.model.step(self.external)
                        self.accumulator -= MODEL_DT
                        steps += 1
                        if time.perf_counter() - budget_start > 0.010:
                            break
                else:
                    self.accumulator = 0.0

                now = time.perf_counter()
                if stamp - self.last_draw >= 1 / 30:
                    self.draw(now)
                    self.last_draw = stamp
                # if stamp - self.last_readout >= 0.20:
                #     self.update_readouts()
                #     self.last_readout = stamp

            self.raf_id = window.requestAnimationFrame(self.animation_proxy)
        except Exception:
            self.report_error()

    def report_error(self):
        self.failed = True
        self.busy = False
        self.running = False
        self.nodes["experiment-controls"].disabled = True
        self.nodes["loading-panel"].hidden = False
        self.nodes["loading-panel"].classList.add("load-error")
        self.text("loading-title", "Die Simulation wurde angehalten.")
        self.text("loading-details", "Bitte Browserkonsole und Dateiversionen prüfen.")
        self.text("run-label", "Angehalten")
        self.nodes["run-dot"].className = "status-dot paused"
        traceback.print_exc()


APP = None
if IN_BROWSER:
    try:
        APP = MagnetApplet()
        START_TASK = asyncio.create_task(APP.start())
    except Exception:
        traceback.print_exc()
        window.magnetLoadFailure("Die Anwendung konnte nicht initialisiert werden.")
elif __name__ == "__main__":
    print("Im gemeinsamen Ordner starten:")
    print("python -m http.server 8000")
    print("Dann im Browser: http://localhost:8000")

