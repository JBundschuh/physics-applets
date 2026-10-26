"""
Rutherford-Streuung – PyScript-Applet
=====================================

Dieses Applet besitzt zwei didaktisch getrennte Darstellungen:

1) Mikroskopische Bahnansicht
   Alphateilchen fliegen von links in ein skaliertes Feld mehrerer Goldatome.
   Die Goldkerne wirken als konzentrierte positive Ladungen.

2) Statistische Versuchsdarstellung
   Ein idealisierter Rutherford-Aufbau mit Quelle, Kollimator, Goldfolie,
   Zählschirm und Winkel-Histogramm. Die Streuwinkel werden über ein
   Stoßparameter-Modell erzeugt.

Wichtige didaktische Einschränkung:
Die Darstellung ist nicht maßstäblich. Kerne, Teilchen, Atomabstände und
Streuwahrscheinlichkeiten sind bewusst skaliert, damit die Effekte im Canvas
sichtbar werden. Es werden keine externen Python-Bibliotheken verwendet.
"""

import math
import random
import time

from js import document, window
from pyodide.ffi import create_proxy


# -----------------------------------------------------------------------------
# DOM und Canvas
# -----------------------------------------------------------------------------

canvas = document.getElementById("simulation-canvas")
ctx = canvas.getContext("2d")
W = int(canvas.width)
H = int(canvas.height)

PROXIES = []  # hält JS-Proxies am Leben


def el(element_id):
    return document.getElementById(element_id)


def query(selector):
    return document.querySelector(selector)


def radio_value(name):
    node = query(f'input[name="{name}"]:checked')
    return str(node.value) if node else ""


def checked(element_id):
    return bool(el(element_id).checked)


def slider_float(element_id):
    return float(el(element_id).value)


def set_text(element_id, value):
    el(element_id).textContent = str(value)


# -----------------------------------------------------------------------------
# Simulationszustand
# -----------------------------------------------------------------------------

state = {
    "running": True,
    "last_timestamp": None,
    "micro_emit_accumulator": 0.0,
    "stats_emit_accumulator": 0.0,
    "particles": [],
    "events": [],
    "flashes": [],
    "total": 0,
    "straight": 0,
    "light": 0,
    "strong": 0,
    "back": 0,
    "hist": [0 for _ in range(18)],  # 18 Klassen à 10°
    "last_theta_deg": 0.0,
    "last_impact": 0.0,
    "start_time": time.time(),
}


# Goldatome: 8 Kerne in versetzter, kfz-artig angedeuteter Anordnung.
# Die Positionen sind bewusst stark vergrößert und nicht maßstäblich.
def make_gold_atoms():
    foil_x = int(W * 0.63)
    foil_y = 28
    foil_w = W - foil_x - 40
    foil_h = H - 56

    # 2D-Darstellung einer regelmäßig versetzten, kfz-artigen Struktur:
    # 4 Reihen mit je 2 Atomen = 8 Goldkerne insgesamt.
    # Jede zweite Reihe ist horizontal um eine halbe Gitterkonstante verschoben.
    rows = 4
    cols = 2

    dx = foil_w * 0.34   # horizontaler Abstand innerhalb einer Reihe
    dy = foil_h * 0.22   # vertikaler Reihenabstand
    shift = dx * 0.5     # Versatz jeder zweiten Reihe

    # Startposition so wählen, dass alles schön innerhalb der Folienfläche liegt
    start_x = foil_x + foil_w * 0.18
    start_y = foil_y + foil_h * 0.18

    atoms = []
    for row in range(rows):
        y = start_y + row * dy
        row_shift = shift if (row % 2 == 1) else 0.0

        for col in range(cols):
            x = start_x + row_shift + col * dx
            atoms.append((x, y))

    return atoms
    
GOLD_ATOMS = make_gold_atoms()

# -----------------------------------------------------------------------------
# Datenklassen ohne externe Bibliotheken
# -----------------------------------------------------------------------------

class AlphaParticle:
    def __init__(self, x, y, vx, vy):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.ax = 0.0
        self.ay = 0.0
        self.trail = [(x, y)]
        self.age = 0.0
        self.alive = True
        self.closest_distance = 1e9

    def add_trail_point(self):
        self.trail.append((self.x, self.y))
        if len(self.trail) > 95:
            self.trail.pop(0)


class ScatterEvent:
    def __init__(self, theta_signed, theta_abs_deg, impact):
        self.theta_signed = theta_signed
        self.theta_abs_deg = theta_abs_deg
        self.impact = impact
        self.age = 0.0

        # große Winkel länger sichtbar
        if theta_abs_deg >= 90:
            self.life = 4.2
        elif theta_abs_deg >= 30:
            self.life = 3.0
        elif theta_abs_deg >= 5:
            self.life = 1.6
        else:
            self.life = 0.85

class DetectorFlash:
    def __init__(self, x, y, theta_abs_deg):
        self.x = x
        self.y = y
        self.theta_abs_deg = theta_abs_deg
        self.age = 0.0

        # Sichtbarkeit des Lichtblitzes verlängert
        if theta_abs_deg >= 90:
            self.life = 3.8
        elif theta_abs_deg >= 30:
            self.life = 2.6
        elif theta_abs_deg >= 5:
            self.life = 1.3
        else:
            self.life = 0.55


# -----------------------------------------------------------------------------
# Parameter und Hilfsfunktionen
# -----------------------------------------------------------------------------

def current_params():
    return {
        "mode": radio_value("mode"),
        "energy": slider_float("energy"),
        "charge": slider_float("charge"),
        "rate": slider_float("rate"),
        "speed": slider_float("speed"),
        "thickness": slider_float("thickness"),
        "show_trails": checked("show-trails"),
        "show_potential": checked("show-potential"),
        "log_histogram": checked("log-histogram"),
    }


def clamp(value, lo, hi):
    return max(lo, min(hi, value))


def length(x, y):
    return math.sqrt(x * x + y * y)

def relative_gold_thickness(params):
    # Referenzwert für die Statistikansicht: 400 nm entspricht ungefähr Goldfolie
    thickness_nm = params["thickness"]
    return max(0.05, thickness_nm / 400.0)

def foil_bounds():
    # Gemeinsamer Materialbereich der Goldfolie in der mikroskopischen Ansicht.
    # Die Folie ist ein vertikaler Streifen rechts im Canvas.
    foil_x = int(W * 0.63)
    foil_w = W - foil_x - 40
    return foil_x, foil_x + foil_w


def in_foil_material(x):
    # Harte didaktische Modellgrenze:
    # Vor und hinter der Folie bewegen sich Alphateilchen wechselwirkungsfrei.
    left, right = foil_bounds()
    return left <= x <= right


def material_edge_factor(x):
    # Weiche Einschaltfunktion an den Folienrändern.
    # Dadurch springt die Kraft nicht abrupt an, wenn ein Teilchen die Folie erreicht.
    left, right = foil_bounds()
    edge = 18.0

    if x < left or x > right:
        return 0.0

    if x < left + edge:
        return (x - left) / edge

    if x > right - edge:
        return (right - x) / edge

    return 1.0


def draw_line(x1, y1, x2, y2, color="#000", width=1.0, alpha=1.0):
    ctx.save()
    ctx.globalAlpha = alpha
    ctx.strokeStyle = color
    ctx.lineWidth = width
    ctx.beginPath()
    ctx.moveTo(x1, y1)
    ctx.lineTo(x2, y2)
    ctx.stroke()
    ctx.restore()


def draw_circle(x, y, r, fill="#000", stroke=None, width=1.0, alpha=1.0):
    ctx.save()
    ctx.globalAlpha = alpha
    ctx.beginPath()
    ctx.arc(x, y, r, 0, 2 * math.pi)
    if fill is not None:
        ctx.fillStyle = fill
        ctx.fill()
    if stroke is not None:
        ctx.strokeStyle = stroke
        ctx.lineWidth = width
        ctx.stroke()
    ctx.restore()


def draw_text(text, x, y, size=14, color="#172033", align="left", weight="400"):
    ctx.save()
    ctx.font = f"{weight} {size}px system-ui, sans-serif"
    ctx.fillStyle = color
    ctx.textAlign = align
    ctx.textBaseline = "middle"
    ctx.fillText(text, x, y)
    ctx.restore()


def draw_arrow(x1, y1, x2, y2, color="#1f2937", width=2.0, alpha=1.0):
    draw_line(x1, y1, x2, y2, color, width, alpha)
    angle = math.atan2(y2 - y1, x2 - x1)
    size = 9
    ctx.save()
    ctx.globalAlpha = alpha
    ctx.fillStyle = color
    ctx.beginPath()
    ctx.moveTo(x2, y2)
    ctx.lineTo(x2 - size * math.cos(angle - 0.45), y2 - size * math.sin(angle - 0.45))
    ctx.lineTo(x2 - size * math.cos(angle + 0.45), y2 - size * math.sin(angle + 0.45))
    ctx.closePath()
    ctx.fill()
    ctx.restore()


def clear_canvas():
    ctx.clearRect(0, 0, W, H)
    ctx.fillStyle = "#fbfcfe"
    ctx.fillRect(0, 0, W, H)


# -----------------------------------------------------------------------------
# Physik: mikroskopische Ansicht
# -----------------------------------------------------------------------------

def spawn_micro_particle(params):
    energy_mev = params["energy"]
    # Höhere Energie -> höhere Geschwindigkeit -> weniger Ablenkung.
    speed = 230.0 + 42.0 * math.sqrt(energy_mev)
    
    y = random.uniform(78, H - 78)
    state["particles"].append(AlphaParticle(36, y, speed, 0.0))


# Kraft im Rutherford-Modell: didaktisch skalierte Coulomb-Abstoßung.
def rutherford_acceleration(x, y, params):
    # Außerhalb der Goldfolie: keine Wechselwirkung.
    # Innerhalb der Goldfolie: didaktisch skaliertes Coulomb-Feld der Goldkerne.
    material_factor = material_edge_factor(x)
    if material_factor <= 0.0:
        return 0.0, 0.0, 1e9

    z_alpha = 2.0 # Heliumkern / Alpha-Teilchen
    z_target = params["charge"]

    # Didaktisch skalierte Coulomb-Stärke.
    k_eff = 300.0

    # Numerische Glättung gegen Singularität.
    softening = 9.0

    ax = 0.0
    ay = 0.0
    closest = 1e9

    for gx, gy in GOLD_ATOMS:
        dx = x - gx
        dy = y - gy
        r2 = dx * dx + dy * dy
        r_real = math.sqrt(r2)
        closest = min(closest, r_real)

        r_eff = math.sqrt(r2 + softening * softening)

        # Vektorielle Coulomb-Abstoßung:
        # F ~ k_eff * Z_alpha * Z_target * r_vec / r_eff^3
        factor = material_factor * k_eff * z_alpha * z_target / (r_eff ** 3)

        ax += factor * dx
        ay += factor * dy

    # Stabilitätsbegrenzung für Canvas-Simulation.
    max_a = 3600.0
    a = length(ax, ay)
    if a > max_a:
        ax *= max_a / a
        ay *= max_a / a

    return ax, ay, closest


def apply_close_reflection(particle):
    # Nahbereichsreflexion nur innerhalb des Materialstreifens.
    if not in_foil_material(particle.x):
        return

    for gx, gy in GOLD_ATOMS:
        dx = particle.x - gx
        dy = particle.y - gy
        r = max(1.0, math.sqrt(dx * dx + dy * dy))

        # Nur bei sehr naher Kernannäherung reflektieren.
        if r < 8.0:
            nx = dx / r
            ny = dy / r
            v_rad = particle.vx * nx + particle.vy * ny

            if v_rad < 0:
                particle.vx -= 2.15 * v_rad * nx
                particle.vy -= 2.15 * v_rad * ny
                particle.x = gx + nx * 9.0
                particle.y = gy + ny * 9.0


def update_micro(dt, params):
    if state["running"]:
        state["micro_emit_accumulator"] += params["rate"] * dt
        while state["micro_emit_accumulator"] >= 1.0:
            if len(state["particles"]) < 130:
                spawn_micro_particle(params)
            state["micro_emit_accumulator"] -= 1.0

        for p in state["particles"]:
            ax, ay, closest = rutherford_acceleration(p.x, p.y, params)
            p.ax = ax
            p.ay = ay
            p.closest_distance = min(p.closest_distance, closest)

            p.vx += ax * dt
            p.vy += ay * dt

            # Geschwindigkeitsbegrenzung verhindert unphysikalische Sprünge im Canvas.
            v = length(p.vx, p.vy)
            if v > 740.0:
                p.vx *= 740.0 / v
                p.vy *= 740.0 / v

            p.x += p.vx * dt
            p.y += p.vy * dt
            p.age += dt

            apply_close_reflection(p)

            p.add_trail_point()
            if p.x < -130 or p.x > W + 130 or p.y < -130 or p.y > H + 130 or p.age > 13:
                p.alive = False

        state["particles"] = [p for p in state["particles"] if p.alive]


# -----------------------------------------------------------------------------
# Physik: Statistikansicht über Stoßparameter
# -----------------------------------------------------------------------------

def sample_impact_parameter(params):
    relative_thickness = relative_gold_thickness(params)  # d = 400 nm -> relative_thickness = 1
    # thickness = params["thickness"]
    
    # geometrische Ziehung des Stoßparameters
    # b_max sinkt bei größerer Targetdichte/Foliendicke
    b_min = 0.055
    b_max = 6.0 / math.sqrt(relative_thickness)

    u = random.random()
    b = math.sqrt(b_min * b_min + u * (b_max * b_max - b_min * b_min))

    sign = -1.0 if random.random() < 0.5 else 1.0
    return sign * b


def sample_rutherford_angle(params):
    energy_mev = params["energy"]
    z_target = params["charge"]
    relative_thickness = relative_gold_thickness(params)

    # Relative Streuwahrscheinlichkeit. - Das ist keine echte SI-Foliendicke, sondern eine didaktische Skalierung.
    scatter_probability = 0.075 * relative_thickness
    scatter_probability = clamp(scatter_probability, 0.0, 0.32)

    # Die meisten Alphateilchen gehen nahezu gerade durch.
    if random.random() > scatter_probability:
        theta_deg = abs(random.gauss(0.0, 0.6))
        theta_deg = clamp(theta_deg, 0.0, 3.0)
        sign = -1.0 if random.random() < 0.5 else 1.0
        return math.radians(sign * theta_deg), theta_deg, 99.0

    # Relevante Kernnähe: Streuwinkel aus dem Stoßparameter-Modell.
    impact = sample_impact_parameter(params)
    b = abs(impact)

    # Skaliertes C ∝ Z_target.
    # Keine SI-Rechnung, sondern didaktische Rutherford-artige Streuformel.
    c = 1.04 * (z_target / 79.0)

    theta_abs = 2.0 * math.atan(c / (energy_mev * b))
    theta_abs = min(theta_abs, math.pi - 0.004)
    theta_signed = math.copysign(theta_abs, impact)

    return theta_signed, math.degrees(theta_abs), b

def register_event(theta_signed, theta_abs_deg, impact):
    state["total"] += 1
    state["last_theta_deg"] = theta_abs_deg
    state["last_impact"] = impact

    if theta_abs_deg < 5:
        state["straight"] += 1
    elif theta_abs_deg < 30:
        state["light"] += 1
    elif theta_abs_deg < 90:
        state["strong"] += 1
    else:
        state["back"] += 1

    bin_index = int(theta_abs_deg // 10)
    bin_index = int(clamp(bin_index, 0, len(state["hist"]) - 1))
    state["hist"][bin_index] += 1

    event = ScatterEvent(theta_signed, theta_abs_deg, impact)
    state["events"].append(event)
    if len(state["events"]) > 90:
        state["events"].pop(0)

    # Trefferpunkt auf kreisförmigem Zählschirm.
    cx, cy = stats_center()
    radius = stats_detector_radius()
    hit_x = cx + radius * math.cos(theta_signed)
    hit_y = cy + radius * math.sin(theta_signed)
    state["flashes"].append(DetectorFlash(hit_x, hit_y, theta_abs_deg))
    if len(state["flashes"]) > 80:
        state["flashes"].pop(0)


def update_statistics(dt, params):
    if state["running"]:
        # In der Statistikansicht dürfen pro Bild mehrere Teilchen verarbeitet werden.
        state["stats_emit_accumulator"] += params["rate"] * dt
        max_batch = 8
        processed = 0
        while state["stats_emit_accumulator"] >= 1.0 and processed < max_batch:
            theta_signed, theta_abs_deg, impact = sample_rutherford_angle(params)
            register_event(theta_signed, theta_abs_deg, impact)
            state["stats_emit_accumulator"] -= 1.0
            processed += 1

    for event in state["events"]:
        event.age += dt
    state["events"] = [e for e in state["events"] if e.age <= e.life]

    for flash in state["flashes"]:
        flash.age += dt
    state["flashes"] = [f for f in state["flashes"] if f.age <= f.life]


# -----------------------------------------------------------------------------
# Zeichnen: gemeinsame Elemente
# -----------------------------------------------------------------------------

def draw_panel_background():
    clear_canvas()
    # dezentes Raster für räumliche Orientierung
    ctx.save()
    ctx.strokeStyle = "rgba(148, 163, 184, 0.16)"
    ctx.lineWidth = 1
    for x in range(0, W + 1, 50):
        ctx.beginPath()
        ctx.moveTo(x, 0)
        ctx.lineTo(x, H)
        ctx.stroke()
    for y in range(0, H + 1, 50):
        ctx.beginPath()
        ctx.moveTo(0, y)
        ctx.lineTo(W, y)
        ctx.stroke()
    ctx.restore()


def draw_badge(text, x, y, fill="#eef2ff", stroke="#c7d2fe", color="#172033"):
    ctx.save()
    ctx.font = "600 13px system-ui, sans-serif"
    width = ctx.measureText(text).width + 22
    height = 28
    ctx.fillStyle = fill
    ctx.strokeStyle = stroke
    ctx.lineWidth = 1
    round_rect(x, y, width, height, 10)
    ctx.fill()
    ctx.stroke()
    ctx.fillStyle = color
    ctx.textBaseline = "middle"
    ctx.fillText(text, x + 11, y + height / 2)
    ctx.restore()


def round_rect(x, y, w, h, r):
    ctx.beginPath()
    ctx.moveTo(x + r, y)
    ctx.lineTo(x + w - r, y)
    ctx.quadraticCurveTo(x + w, y, x + w, y + r)
    ctx.lineTo(x + w, y + h - r)
    ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h)
    ctx.lineTo(x + r, y + h)
    ctx.quadraticCurveTo(x, y + h, x, y + h - r)
    ctx.lineTo(x, y + r)
    ctx.quadraticCurveTo(x, y, x + r, y)
    ctx.closePath()


# -----------------------------------------------------------------------------
# Zeichnen: mikroskopische Ansicht
# -----------------------------------------------------------------------------

def draw_potential_field():
    # Qualitative Darstellung des Coulomb-Wirkungsbereichs.
    foil_left, foil_right = foil_bounds()

    ctx.save()

    # Auf die sichtbare Goldfolie begrenzen.
    ctx.beginPath()
    ctx.rect(foil_left, 0, foil_right - foil_left, H)
    ctx.clip()

    for gx, gy in GOLD_ATOMS:
        # Radialer Halo um jeden Goldkern: Das ist keine SI-genaue Potentialkarte, sondern eine didaktische Feldanzeige.
        radius = 82

        gradient = ctx.createRadialGradient(gx, gy, 4, gx, gy, radius)
        gradient.addColorStop(0.00, "rgba(180, 83, 9, 0.42)")
        gradient.addColorStop(0.16, "rgba(234, 179, 8, 0.32)")
        gradient.addColorStop(0.38, "rgba(250, 204, 21, 0.18)")
        gradient.addColorStop(0.70, "rgba(251, 191, 36, 0.08)")
        gradient.addColorStop(1.00, "rgba(251, 191, 36, 0.00)")

        ctx.fillStyle = gradient
        ctx.beginPath()
        ctx.arc(gx, gy, radius, 0, 2 * math.pi)
        ctx.fill()

    ctx.restore()


def draw_micro_setup(params):
    # Quelle links
    ctx.save()
    grad = ctx.createLinearGradient(0, 0, 96, 0)
    grad.addColorStop(0, "rgba(51, 65, 85, 0.18)")
    grad.addColorStop(1, "rgba(51, 65, 85, 0.02)")
    ctx.fillStyle = grad
    ctx.fillRect(0, 0, 118, H)
    ctx.restore()

    draw_text("α-Quelle", 34, 38, 15, "#334155", "left", "700")
 


    # Goldfolie als Materialstreifen:
    # Der sichtbare Goldbereich ist exakt derselbe Bereich,
    # in dem im Rutherford-Modell die Wechselwirkung berechnet wird.
    foil_left, foil_right = foil_bounds()
    foil_w = foil_right - foil_left

    ctx.save()

    grad2 = ctx.createLinearGradient(foil_left, 0, foil_right, 0)
    grad2.addColorStop(0.0, "rgba(245, 158, 11, 0.035)")
    grad2.addColorStop(0.16, "rgba(245, 158, 11, 0.10)")
    grad2.addColorStop(0.50, "rgba(251, 191, 36, 0.14)")
    grad2.addColorStop(0.84, "rgba(245, 158, 11, 0.10)")
    grad2.addColorStop(1.0, "rgba(245, 158, 11, 0.035)")
    ctx.fillStyle = grad2

    # Der Materialbereich reicht sichtbar über den oberen und unteren Rand hinaus.
    # Canvas clippt automatisch am Rand.
    ctx.fillRect(foil_left, -40, foil_w, H + 80)

    # Diese beiden Linien markieren zugleich:
    # linke/rechte Grenze der Goldfolie UND linke/rechte Grenze der Wechselwirkungszone.
    draw_line(foil_left, -30, foil_left, H + 30, "#b45309", 2.2, 0.36)
    draw_line(foil_right, -30, foil_right, H + 30, "#b45309", 2.0, 0.26)

    # Fortsetzungsmarkierungen oben/unten: Material geht weiter.
    for x in [foil_left + 18, foil_left + 44, foil_left + 70, foil_left + 96]:
        draw_line(x, 8, x + 18, -12, "#92400e", 1.4, 0.30)
        draw_line(x, H - 8, x + 18, H + 12, "#92400e", 1.4, 0.30)

    ctx.restore()

    draw_text("Goldfolie", foil_left + 16, 86, 14, "#92400e", "left", "700")

def draw_gold_atoms():
    """Zeichnet die Goldkerne und die schematischen Atomhüllen."""
    for gx, gy in GOLD_ATOMS:
        gradient = ctx.createRadialGradient(gx, gy, 3, gx, gy, 34)
        gradient.addColorStop(0, "rgba(250, 204, 21, 0.24)")
        gradient.addColorStop(1, "rgba(250, 204, 21, 0.030)")

        ctx.save()
        ctx.fillStyle = gradient
        ctx.beginPath()
        ctx.arc(gx, gy, 35, 0, 2 * math.pi)
        ctx.fill()
        ctx.strokeStyle = "rgba(180, 83, 9, 0.28)"
        ctx.lineWidth = 1.2
        ctx.stroke()
        ctx.restore()

        draw_circle(gx, gy, 8.5, "#facc15", "#92400e", 1.5)
        draw_circle(gx - 2, gy - 3, 2.4, "rgba(255,255,255,0.72)")


def draw_particles(params):
    for p in state["particles"]:
        if params["show_trails"] and len(p.trail) > 1:
            ctx.save()
            ctx.lineWidth = 2
            for i in range(1, len(p.trail)):
                alpha = i / len(p.trail)
                ctx.strokeStyle = f"rgba(37, 99, 235, {0.08 + 0.42 * alpha})"
                ctx.beginPath()
                ctx.moveTo(p.trail[i - 1][0], p.trail[i - 1][1])
                ctx.lineTo(p.trail[i][0], p.trail[i][1])
                ctx.stroke()
            ctx.restore()

        draw_circle(p.x, p.y, 4.5, "#2563eb", "#1e40af", 1.2)
        draw_text("α", p.x, p.y + 0.1, 9, "white", "center", "800")

 
def draw_micro_annotations():
    draw_badge("Rutherford-Modell", 18, 18, "#f8fafc", "#cbd5e1")
    draw_text("Coulomb-Abstoßung innerhalb der Goldfolie", W * 0.52, 34, 15, "#7c2d12", "center", "700")
    draw_text("Nicht maßstäblich", W / 2, H - 26, 14, "#64748b", "center")


def draw_micro(params):
    draw_panel_background()
    if params["show_potential"]:
        draw_potential_field()
    draw_micro_setup(params)
    draw_gold_atoms()
    draw_particles(params)
    draw_micro_annotations()


# -----------------------------------------------------------------------------
# Zeichnen: Statistikansicht
# -----------------------------------------------------------------------------

def stats_center():
    return 345, int(H * 0.52)


def stats_detector_radius():
    return 235


def draw_statistics_setup(params):
    cx, cy = stats_center()
    radius = stats_detector_radius()

    # linker Bereich: Aufbau
    ctx.save()
    ctx.fillStyle = "rgba(248, 250, 252, 0.84)"
    ctx.strokeStyle = "rgba(203, 213, 225, 0.9)"
    ctx.lineWidth = 1.5
    round_rect(22, 70, 610, 512, 18)
    ctx.fill()
    ctx.stroke()
    ctx.restore()

    draw_text("Versuchsaufbau", 42, 96, 16, "#334155", "left", "800")

    # Quelle und Kollimator
    draw_circle(78, cy, 27, "#334155", "#0f172a", 1.5)
    draw_text("α", 78, cy, 19, "#ffffff", "center", "800")
    draw_text("Quelle", 78, cy + 48, 13, "#475569", "center")

    ctx.save()
    ctx.fillStyle = "#475569"
    ctx.fillRect(136, cy - 34, 14, 25)
    ctx.fillRect(136, cy + 9, 14, 25)
    ctx.restore()
    draw_text("Kollimator", 143, cy + 56, 13, "#475569", "center")
    draw_arrow(108, cy, cx - 25, cy, "#2563eb", 2.4, 0.75)

    # Goldfolie
    ctx.save()
    ctx.strokeStyle = "#d97706"
    ctx.lineWidth = 5
    ctx.beginPath()
    ctx.moveTo(cx, cy - 70)
    ctx.lineTo(cx, cy + 70)
    ctx.stroke()
    ctx.restore()
    draw_circle(cx, cy, 12, "#facc15", "#92400e", 1.5)
    draw_text("Goldfolie", cx, cy + 92, 13, "#92400e", "center", "700")

    # Zählschirm
    ctx.save()
    ctx.strokeStyle = "rgba(15, 23, 42, 0.35)"
    ctx.lineWidth = 3
    ctx.setLineDash([9, 7])
    ctx.beginPath()
    ctx.arc(cx, cy, radius, -math.pi, math.pi)
    ctx.stroke()
    ctx.setLineDash([])
    ctx.restore()
    draw_text("Zählschirm", cx, cy - radius - 24, 14, "#334155", "center", "700")

    # Winkelmarken
    for deg in [-150, -90, -30, 0, 30, 90, 150]:
        a = math.radians(deg)
        x1 = cx + (radius - 8) * math.cos(a)
        y1 = cy + (radius - 8) * math.sin(a)
        x2 = cx + (radius + 8) * math.cos(a)
        y2 = cy + (radius + 8) * math.sin(a)
        draw_line(x1, y1, x2, y2, "rgba(51, 65, 85, 0.55)", 1.5, 1)
        if deg in [-90, 0, 90]:
            lx = cx + (radius + 28) * math.cos(a)
            ly = cy + (radius + 28) * math.sin(a)
            label = f"{abs(deg)}°" if deg != 0 else "0°"
            draw_text(label, lx, ly, 12, "#64748b", "center")


def event_color(theta_abs_deg):
    if theta_abs_deg >= 90:
        return "#dc2626"
    if theta_abs_deg >= 30:
        return "#ea580c"
    if theta_abs_deg >= 5:
        return "#ca8a04"
    return "#2563eb"


def draw_scatter_events():
    cx, cy = stats_center()
    radius = stats_detector_radius()

    for event in state["events"]:
        alpha = max(0.0, 1.0 - event.age / event.life)
        color = event_color(event.theta_abs_deg)
        # eingehender Strahl
        draw_line(104, cy, cx, cy, "#2563eb", 1.4, 0.12 * alpha)
        # ausgehende Bahn
        end_x = cx + radius * math.cos(event.theta_signed)
        end_y = cy + radius * math.sin(event.theta_signed)
        draw_line(cx, cy, end_x, end_y, color, 2.0, 0.55 * alpha)

    for flash in state["flashes"]:
        alpha = max(0.0, 1.0 - flash.age / flash.life)
        color = event_color(flash.theta_abs_deg)
        draw_circle(flash.x, flash.y, 5 + 8 * (1 - alpha), None, color, 2.0, alpha)
        draw_circle(flash.x, flash.y, 3.5, color, None, 1.0, alpha)


def draw_histogram(params):
    x0 = 682
    y0 = 96
    width = 338
    height = 430
    pad_left = 44
    pad_bottom = 40
    plot_x = x0 + pad_left
    plot_y = y0 + 28
    plot_w = width - pad_left - 18
    plot_h = height - pad_bottom - 48

    ctx.save()
    ctx.fillStyle = "rgba(255, 255, 255, 0.90)"
    ctx.strokeStyle = "rgba(203, 213, 225, 0.9)"
    ctx.lineWidth = 1.5
    round_rect(x0, y0, width, height, 18)
    ctx.fill()
    ctx.stroke()
    ctx.restore()

    title = "Winkel-Histogramm"
    draw_text(title, x0 + 18, y0 + 22, 16, "#334155", "left", "800")
    scale_label = "logarithmisch" if params["log_histogram"] else "linear"
    draw_text(scale_label, x0 + width - 18, y0 + 22, 12, "#64748b", "right")

    counts = state["hist"]
    if params["log_histogram"]:
        values = [math.log10(c + 1) for c in counts]
    else:
        values = list(counts)
    vmax = max(values) if values else 1
    vmax = max(vmax, 1e-9)

    # Achsen
    draw_line(plot_x, plot_y, plot_x, plot_y + plot_h, "#94a3b8", 1.2)
    draw_line(plot_x, plot_y + plot_h, plot_x + plot_w, plot_y + plot_h, "#94a3b8", 1.2)

    # Hilfslinien
    for i in range(1, 5):
        yy = plot_y + plot_h * (1 - i / 5)
        draw_line(plot_x, yy, plot_x + plot_w, yy, "rgba(148, 163, 184, 0.20)", 1)

    bar_gap = 3
    bar_w = (plot_w - bar_gap * (len(counts) - 1)) / len(counts)
    for i, raw_count in enumerate(counts):
        value = values[i]
        h = 0 if value <= 0 else plot_h * (value / vmax)
        bx = plot_x + i * (bar_w + bar_gap)
        by = plot_y + plot_h - h
        if i >= 9:
            color = "#dc2626"
        elif i >= 3:
            color = "#ea580c"
        elif i >= 1:
            color = "#ca8a04"
        else:
            color = "#2563eb"
        ctx.save()
        ctx.fillStyle = color
        ctx.globalAlpha = 0.78
        ctx.fillRect(bx, by, bar_w, h)
        ctx.restore()

    # x-Beschriftung
    for deg in [0, 30, 60, 90, 120, 150, 180]:
        px = plot_x + plot_w * deg / 180
        draw_line(px, plot_y + plot_h, px, plot_y + plot_h + 5, "#94a3b8", 1)
        draw_text(str(deg), px, plot_y + plot_h + 20, 11, "#64748b", "center")
    draw_text("Streuwinkel θ", plot_x + plot_w / 2, y0 + height - 12, 12, "#64748b", "center", "700")

    # Kurzer Messwertblock
    draw_text(f"letzter Winkel: {state['last_theta_deg']:.1f}°", x0 + 18, y0 + height + 22, 13, "#334155", "left", "700")
    draw_text(f"Stoßparameter b: {state['last_impact']:.2f} arb.", x0 + 18, y0 + height + 44, 13, "#64748b", "left")


def draw_statistics_annotations():
    draw_badge("Rutherford-Streuung", 22, 18, "#f8fafc", "#cbd5e1")
    draw_badge("θ = 2 arctan(C / E·b)", 218, 18, "#fff7ed", "#fed7aa", "#7c2d12")
    draw_badge("Ungewichtete Zählung", 462, 18, "#f8fafc", "#cbd5e1", "#334155")
    draw_text("Streuwinkelstatistik ohne Darstellung einzelner Atome", W / 2, H - 24, 14, "#64748b", "center")


def draw_statistics(params):
    draw_panel_background()
    draw_statistics_setup(params)
    draw_scatter_events()
    draw_histogram(params)
    draw_statistics_annotations()


# -----------------------------------------------------------------------------
# UI-Aktualisierung
# -----------------------------------------------------------------------------

def update_control_visibility(params):
    mode = params["mode"]

    micro_options = el("micro-options")
    stats_options = el("stats-options")
    count_panel = el("count-panel")

    if mode == "micro":
        micro_options.style.display = "block"
        stats_options.style.display = "none"
        count_panel.style.display = "none"
    else:
        micro_options.style.display = "none"
        stats_options.style.display = "block"
        count_panel.style.display = "block"

def update_readouts(params):
    update_control_visibility(params)
    
    set_text("energy-value", f"{params['energy']:.1f}")
    set_text("charge-value", f"{int(params['charge'])}")
    set_text("rate-value", f"{int(params['rate'])}")
    set_text("speed-value", f"{params['speed']:.2g}")
    set_text("thickness-value", f"{int(params['thickness'])}")

    set_text("count-total", state["total"])
    set_text("count-straight", state["straight"])
    set_text("count-light", state["light"])
    set_text("count-strong", state["strong"])
    set_text("count-back", state["back"])

    mode = params["mode"]
    if mode == "micro":
        info = "Qualitatives Coulombfeld der Goldkerne innerhalb der Folie."
    else:
        info = "Kleine Stoßparameter führen zu großen, seltenen Streuwinkeln."

    set_text("info-text", info)

    runtime = max(0.1, time.time() - state["start_time"])
    if mode == "micro":
        set_text("status-line", f"Bahnansicht · α-Teilchen: {len(state['particles'])} · Laufzeit: {runtime:.0f} s")
    else:
        set_text("status-line", f"Statistik · Teilchen: {state['total']} · letzter Winkel: {state['last_theta_deg']:.1f}°")

def reset_state(_event=None):
    state["micro_emit_accumulator"] = 0.0
    state["stats_emit_accumulator"] = 0.0
    state["particles"] = []
    state["events"] = []
    state["flashes"] = []
    state["total"] = 0
    state["straight"] = 0
    state["light"] = 0
    state["strong"] = 0
    state["back"] = 0
    state["hist"] = [0 for _ in range(18)]
    state["last_theta_deg"] = 0.0
    state["last_impact"] = 0.0
    state["start_time"] = time.time()


def toggle_running(_event=None):
    state["running"] = not state["running"]
    el("start-pause").textContent = "Pause" if state["running"] else "Start"


def on_mode_change(_event=None):
    # Beim Wechsel der Ansicht beginnen die Zählungen erneut.
    reset_state()


def add_event_listener(element_id, event_name, func):
    proxy = create_proxy(func)
    PROXIES.append(proxy)
    el(element_id).addEventListener(event_name, proxy)


def add_radio_listeners(name):
    nodes = document.querySelectorAll(f'input[name="{name}"]')
    for i in range(int(nodes.length)):
        proxy = create_proxy(on_mode_change)
        PROXIES.append(proxy)
        nodes.item(i).addEventListener("change", proxy)


def initialize_ui():
    add_event_listener("start-pause", "click", toggle_running)
    add_event_listener("reset", "click", reset_state)
    add_radio_listeners("mode")

    # Slider und Checkboxen benötigen keine eigene Logik; Werte werden pro Frame gelesen.
    set_text("status-line", "Simulation bereit.")


# -----------------------------------------------------------------------------
# Hauptschleife
# -----------------------------------------------------------------------------

def animation_frame(timestamp):
    params = current_params()

    if state["last_timestamp"] is None:
        state["last_timestamp"] = float(timestamp)
    raw_dt = (float(timestamp) - state["last_timestamp"]) / 1000.0
    state["last_timestamp"] = float(timestamp)

    # Große dt-Sprünge nach Tab-Wechseln abfangen.
    dt = clamp(raw_dt, 0.0, 0.04) * params["speed"]

    if params["mode"] == "micro":
        update_micro(dt, params)
        draw_micro(params)
    else:
        update_statistics(dt, params)
        draw_statistics(params)

    update_readouts(params)
    window.requestAnimationFrame(ANIMATION_PROXY)


initialize_ui()
ANIMATION_PROXY = create_proxy(animation_frame)
PROXIES.append(ANIMATION_PROXY)
window.requestAnimationFrame(ANIMATION_PROXY)
