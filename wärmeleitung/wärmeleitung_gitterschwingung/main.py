"""
Temperaturfeld-Wärmeleitung
===========================

Dieses PyScript-Applet zeigt ein bewusst vereinfachtes Modell für
Wärmeleitung in einem Festkörper.

Didaktische Kernidee
--------------------
Ein Festkörper wird als 10 x 10 Gitter aus Knoten dargestellt. Die Knoten
können sich in x- und y-Richtung bewegen. Benachbarte Knoten sind über
sichtbare Federn gekoppelt. Dadurch kann Bewegungsenergie von einem warmen
Bereich in benachbarte kältere Bereiche übertragen werden.

Wichtig: Das ist keine exakte Atomsimulation. Jeder Knoten steht modellhaft
für einen Gitterplatz bzw. kleinen Bereich des Festkörpers. Die lokale
"Modelltemperatur" wird aus der kinetischen Energie des Knotens bestimmt:

    T_modell ~ vx² + vy²

Damit ist ein heißer Knoten ein Knoten mit großer ungeordneter Bewegung.

Warum zufällige Streuung?
-------------------------
Ein reines Feder-Masse-Gitter würde sehr geordnete mechanische Wellen zeigen.
Für Wärmeleitung möchten wir aber eine ungeordnete thermische Bewegung
modellieren. Deshalb wird die Richtung der Geschwindigkeit regelmäßig zufällig
verändert, während der Betrag der Geschwindigkeit gleich bleibt.

Diese Streuung erhält die kinetische Energie des einzelnen Knotens und hilft,
geordnete Wellenbewegung in eine stärker thermische Bewegung zu überführen.

Warum eine unsichtbare Feder zur Gleichgewichtslage?
---------------------------------------------------
Die sichtbaren Federn koppeln Nachbarknoten. Zusätzlich gibt es eine schwache,
unsichtbare Rückstellfeder zur jeweiligen Ruhelage des Knotens. Diese verhindert,
dass das gesamte Gitter aus dem sichtbaren Bereich driftet, ohne einzelne
Freiheitsgrade fest zu sperren. Auch diese Federenergie wird in der
Gesamtenergie mitgezählt.

PyScript-Kompatibilität
-----------------------
Es wird nur Standard-Python verwendet. Keine externen Pakete wie NumPy.
"""

from math import sqrt, cos, sin, pi
from random import random
from js import document, window
from pyodide.ffi import create_proxy


# ---------------------------------------------------------------------------
# Robuste DOM-Hilfsfunktionen
# ---------------------------------------------------------------------------


def el(element_id):
    """HTML-Element per id holen.

    Pyodide kann ein JavaScript-null als JsNull-Objekt liefern. Deshalb prüfen
    wir zusätzlich auf diese Typnamen. Das verhindert Fehler der Form
    "AttributeError: 'JsNull' object has no attribute ...".
    """
    element = document.getElementById(element_id)

    if element is None:
        return None

    if type(element).__name__ in ("JsNull", "JsUndefined"):
        return None

    if str(element) in ("null", "undefined"):
        return None

    return element


def float_value(element_id, default=0.0):
    """Wert eines Sliders als float lesen."""
    element = el(element_id)
    if element is None:
        return default
    return float(element.value)


def int_value(element_id, default=0):
    """Wert eines Sliders als int lesen."""
    element = el(element_id)
    if element is None:
        return default
    return int(float(element.value))


def is_checked(element_id, default=False):
    """Zustand einer Checkbox lesen."""
    element = el(element_id)
    if element is None:
        return default
    return bool(element.checked)


def set_text(element_id, text):
    """Textinhalt eines Elements setzen, falls es existiert."""
    element = el(element_id)
    if element is not None:
        element.textContent = str(text)


# ---------------------------------------------------------------------------
# Canvas und globale Zustände
# ---------------------------------------------------------------------------


sim_canvas = el("sim_canvas")
sim_ctx = sim_canvas.getContext("2d")
profile_canvas = el("profile_canvas")
profile_ctx = profile_canvas.getContext("2d")

# Hintergrundgitter wird einmal vorgerechnet und dann pro Frame nur kopiert.
background_canvas = document.createElement("canvas")
background_ctx = background_canvas.getContext("2d")

# Anzahl der Knoten pro Richtung.
N = 10
NODE_COUNT = N * N

# Modellparameter. Die Einheiten sind bewusst dimensionslos.
MASS = 1.0
REST_LENGTH = 1.0
BASE_DT = 0.004
TEMP_TO_V2 = 0.006

# Schwache unsichtbare Rückstellfeder zur Gleichgewichtslage.
# Sie dient der Stabilisierung der Darstellung und wird in der Energie mitgezählt.
PIN_STIFFNESS_FACTOR = 0.80
# Nichtlinearer Zusatz der Rückstellfeder.
PIN_NONLINEAR_FACTOR = 6.0

# Die Streuung rotiert Geschwindigkeiten zufällig, ohne deren Betrag zu ändern.
# Größerer Wert -> weniger geordnete Wellen, stärker thermische Bewegung.
SCATTER_PROBABILITY_PER_SUBSTEP = 0.015

# Glättung der angezeigten Modelltemperatur. 0 = keine Anpassung, 1 = sofort.
TEMP_SMOOTHING = 0.08

# Fester Farbreferenzwert pro Knoten (dimensionslose Energie).
# Entspricht der kinetischen Energie bei einer Anfangstemperatur von 120.
ENERGY_COLOR_REFERENCE = 0.5 * MASS * TEMP_TO_V2 * 120.0
DIAGNOSTIC_UPDATE_INTERVAL = 8

# Arrays für Gleichgewichtslagen, Positionen, Geschwindigkeiten und Anzeige-Temperaturen.
x0 = []
y0 = []
x = []
y = []
vx = []
vy = []
temp_smooth = []
ax = []
ay = []
spring_pairs = []

# Energiereferenz nach Reset. Wird zur Anzeige der Energieänderung genutzt.
initial_total_energy = 0.0
last_kinetic_energy = 0.0
last_spring_energy = 0.0
last_total_energy = 0.0

# Zwischengespeicherte Werte für Diagramm und Statistik.
cached_profile_values = [0.0 for _ in range(N)]
cached_node_energies = [0.0 for _ in range(NODE_COUNT)]
cached_mean_temp = 0.0
cached_delta_temp = 0.0

# Animation
is_running = False
last_timestamp = None
frame_counter = 0
_proxies = []


# ---------------------------------------------------------------------------
# Kleine mathematische Hilfsfunktionen
# ---------------------------------------------------------------------------


def clamp(value, low, high):
    """Begrenzt einen Wert auf das Intervall [low, high]."""
    return max(low, min(high, value))


def lerp(a, b, t):
    """Lineare Interpolation zwischen a und b."""
    return a + (b - a) * t


def random_angle():
    """Zufälliger Winkel zwischen 0 und 2*pi."""
    return 2.0 * pi * random()


def temperature_to_speed(temp):
    """Wandelt eine Modelltemperatur in einen Geschwindigkeitsbetrag um.

    Da T_modell proportional zu v² ist, gilt v = sqrt(T * Faktor).
    """
    return sqrt(max(0.0, temp) * TEMP_TO_V2)


def speed_squared_to_temperature(v2):
    """Wandelt v² zurück in die dimensionslose Modelltemperatur."""
    return v2 / TEMP_TO_V2


def current_node_temperature(index):
    """Momentane Modelltemperatur eines Knotens aus vx² + vy²."""
    return speed_squared_to_temperature(vx[index] * vx[index] + vy[index] * vy[index])


def idx(col, row):
    """Wandelt 2D-Indizes in einen linearen Array-Index um."""
    return row * N + col

# ---------------------------------------------------------------------------
# Vorbereitete Listen und Hintergrunddarstellung
# ---------------------------------------------------------------------------


def build_spring_pairs():
    """Erzeugt die Liste aller sichtbaren Nachbarfedern einmalig."""
    global spring_pairs
    spring_pairs = []

    for row in range(N):
        for col in range(N):
            a = idx(col, row)

            if col < N - 1:
                spring_pairs.append((a, idx(col + 1, row)))

            if row < N - 1:
                spring_pairs.append((a, idx(col, row + 1)))


def screen_geometry():
    """Berechnet Skalierung und Randabstände für die Canvas-Darstellung."""
    width = sim_canvas.width
    height = sim_canvas.height
    margin = 74
    usable = min(width - 2 * margin, height - 2 * margin)
    scale = usable / (N - 1)
    left = (width - usable) / 2
    top = (height - usable) / 2 + 12
    return left, top, scale


def render_background_grid():
    """Zeichnet das ruhende Hintergrundgitter einmal auf ein Offscreen-Canvas."""
    background_canvas.width = sim_canvas.width
    background_canvas.height = sim_canvas.height

    background_ctx.clearRect(0, 0, background_canvas.width, background_canvas.height)
    left, top, scale = screen_geometry()

    background_ctx.save()
    background_ctx.strokeStyle = "rgba(120, 135, 160, 0.13)"
    background_ctx.lineWidth = 1
    background_ctx.beginPath()

    for row in range(N):
        y_screen = top + row * scale
        background_ctx.moveTo(left, y_screen)
        background_ctx.lineTo(left + (N - 1) * scale, y_screen)

    for col in range(N):
        x_screen = left + col * scale
        background_ctx.moveTo(x_screen, top)
        background_ctx.lineTo(x_screen, top + (N - 1) * scale)

    background_ctx.stroke()
    background_ctx.restore()


def screen_position_with_geometry(i, left, top, scale):
    """Modellposition eines Knotens in Canvas-Koordinaten umrechnen."""
    return left + x[i] * scale, top + y[i] * scale


# ---------------------------------------------------------------------------
# Simulation initialisieren
# ---------------------------------------------------------------------------


def target_temperature_for_column(col):
    """Starttemperatur abhängig von der Spalte.

    Linke Spalte, rechte Spalte und alle inneren Spalten können getrennt
    eingestellt werden.
    """
    if col == 0:
        return float_value("temp_left_slider", 100.0)
    if col == N - 1:
        return float_value("temp_right_slider", 20.0)
    return float_value("temp_middle_slider", 20.0)


def initialize_lattice():
    """Setzt das Gitter auf den Anfangszustand zurück."""
    global x0, y0, x, y, vx, vy, temp_smooth, ax, ay
    global initial_total_energy, last_kinetic_energy, last_spring_energy, last_total_energy

    x0 = []
    y0 = []
    x = []
    y = []
    vx = []
    vy = []
    temp_smooth = []
    ax = [0.0 for _ in range(NODE_COUNT)]
    ay = [0.0 for _ in range(NODE_COUNT)]

    for row in range(N):
        for col in range(N):
            # Gleichgewichtslage: regelmäßiges 10 x 10 Gitter.
            gx = col * REST_LENGTH
            gy = row * REST_LENGTH
            x0.append(gx)
            y0.append(gy)
            x.append(gx)
            y.append(gy)

            # Anfangstemperatur -> zufällige Geschwindigkeitsrichtung.
            temp = target_temperature_for_column(col)
            speed = temperature_to_speed(temp)
            angle = random_angle()
            vx.append(speed * cos(angle))
            vy.append(speed * sin(angle))
            temp_smooth.append(temp)

    # Nach Reset ist die Anfangsenergie die Referenz.
    update_diagnostics()
    initial_total_energy = last_total_energy
    
    update_labels_and_stats()
    draw_all(force_profile=True)


# ---------------------------------------------------------------------------
# Physik: Kräfte, Energie, Zeitschritt
# ---------------------------------------------------------------------------


def stiffness():
    """Aktuelle Federkopplung aus dem Slider."""
    return float_value("stiffness_slider", 5.0)


def clear_accelerations():
    """Setzt die Beschleunigungsarrays auf null, ohne neue Listen anzulegen."""
    for i in range(NODE_COUNT):
        ax[i] = 0.0
        ay[i] = 0.0


def add_spring_force(a, b, rest_length, k):
    """Addiert die Kraft einer sichtbaren Feder zwischen zwei Knoten."""
    dx_ab = x[b] - x[a]
    dy_ab = y[b] - y[a]
    dist = sqrt(dx_ab * dx_ab + dy_ab * dy_ab)

    if dist < 1e-9:
        return

    extension = dist - rest_length
    force_magnitude = k * extension

    fx = force_magnitude * dx_ab / dist
    fy = force_magnitude * dy_ab / dist

    ax[a] += fx / MASS
    ay[a] += fy / MASS
    ax[b] -= fx / MASS
    ay[b] -= fy / MASS


def compute_forces():
    """Berechnet alle Beschleunigungen für den nächsten Zeitschritt."""
    clear_accelerations()

    k = stiffness()
    k_pin = PIN_STIFFNESS_FACTOR * k

    # Sichtbare Nachbarfedern.
    for a, b in spring_pairs:
        add_spring_force(a, b, REST_LENGTH, k)

    # Unsichtbare nichtlineare Rückstellfedern zur Gleichgewichtslage.
    for i in range(NODE_COUNT):
        dx = x[i] - x0[i]
        dy = y[i] - y0[i]

        r2 = dx * dx + dy * dy
        nonlinear_factor = 1.0 + PIN_NONLINEAR_FACTOR * r2

        ax[i] += -k_pin * nonlinear_factor * dx / MASS
        ay[i] += -k_pin * nonlinear_factor * dy / MASS


def compute_spring_energy_only(energy_by_col=None, energy_by_node=None):
    """Berechnet die Federenergie und optional ihre räumliche Verteilung.

    Nachbarfedern werden hälftig ihren beiden Endknoten zugeordnet.
    Rückstellfedern gehören jeweils zur Spalte ihres Knotens.
    """
    k = stiffness()
    k_pin = PIN_STIFFNESS_FACTOR * k
    energy = 0.0

    # Energie der sichtbaren Nachbarfedern.
    for a, b in spring_pairs:
        dx_ab = x[b] - x[a]
        dy_ab = y[b] - y[a]
        dist = sqrt(dx_ab * dx_ab + dy_ab * dy_ab)
        extension = dist - REST_LENGTH
        spring_energy = 0.5 * k * extension * extension
        energy += spring_energy
        if energy_by_col is not None:
            energy_by_col[a % N] += 0.5 * spring_energy
            energy_by_col[b % N] += 0.5 * spring_energy
        if energy_by_node is not None:
            energy_by_node[a] += 0.5 * spring_energy
            energy_by_node[b] += 0.5 * spring_energy

    # Energie der unsichtbaren nichtlinearen Rückstellfedern.
    for i in range(NODE_COUNT):
        dx = x[i] - x0[i]
        dy = y[i] - y0[i]
        r2 = dx * dx + dy * dy

        pin_energy = (
            0.5 * k_pin * r2
            + 0.25 * k_pin * PIN_NONLINEAR_FACTOR * r2 * r2
        )
        energy += pin_energy
        if energy_by_col is not None:
            energy_by_col[i % N] += pin_energy
        if energy_by_node is not None:
            energy_by_node[i] += pin_energy

    return energy


def scatter_velocity_directions():
    """Energieerhaltende zufällige Streuung der Geschwindigkeitsrichtungen.

    Der Betrag der Geschwindigkeit bleibt gleich. Dadurch bleibt die kinetische
    Energie jedes gestreuten Knotens erhalten, aber die Bewegungsrichtung wird
    ungeordneter. Das reduziert geordnete mechanische Wellenmuster.
    """
    for i in range(NODE_COUNT):
        if random() < SCATTER_PROBABILITY_PER_SUBSTEP:
            speed = sqrt(vx[i] * vx[i] + vy[i] * vy[i])
            angle = random_angle()
            vx[i] = speed * cos(angle)
            vy[i] = speed * sin(angle)


def apply_boundary_thermostats():
    """
    Hält linke und rechte Randtemperatur fest, falls die Checkbox aktiv ist.

    Wichtig:
    Die Randknoten werden NICHT festgehalten.
    Ihre Position bleibt frei beweglich und sie sind weiterhin über Federn
    mit den Nachbarknoten gekoppelt.

    Es wird nur die kinetische Energie der Randknoten auf das gewünschte
    Temperaturniveau skaliert.

    Physikalische Modellidee:
        T_modell ~ vx² + vy²

    Deshalb wird der Geschwindigkeitsbetrag angepasst, die Richtung der
    Geschwindigkeit aber möglichst beibehalten. Dadurch kann weiterhin
    mechanisch Energie über die Federn ins Gitter übertragen werden.
    """
    if not is_checked("thermostat_checkbox", False):
        return

    left_temp = float_value("temp_left_slider", 100.0)
    right_temp = float_value("temp_right_slider", 20.0)

    for row in range(N):
        for col, target_temp in ((0, left_temp), (N - 1, right_temp)):
            i = idx(col, row)

            # Zielwert für v², weil T_modell proportional zu v² ist.
            target_v2 = max(0.0, target_temp) * TEMP_TO_V2

            # Aktueller Geschwindigkeitsbetrag².
            current_v2 = vx[i] * vx[i] + vy[i] * vy[i]

            if current_v2 > 1e-12:
                # Geschwindigkeit skalieren:
                # Richtung bleibt erhalten, Betrag wird auf Zieltemperatur gesetzt.
                scale = sqrt(target_v2 / current_v2)
                vx[i] *= scale
                vy[i] *= scale
            else:
                # Falls ein Knoten zufällig fast ruht, geben wir ihm eine
                # zufällige Richtung mit passendem Betrag.
                speed = sqrt(target_v2)
                angle = random_angle()
                vx[i] = speed * cos(angle)
                vy[i] = speed * sin(angle)

            # Anzeige-Temperatur am Rand schneller an den Zielwert annähern.
            temp_smooth[i] = 0.85 * temp_smooth[i] + 0.15 * target_temp

def update_temperature_smoothing():
    """Aktualisiert geglättete Temperaturen für Farbe und Diagramm."""
    for i in range(NODE_COUNT):
        current_temp = current_node_temperature(i)
        temp_smooth[i] = (1.0 - TEMP_SMOOTHING) * temp_smooth[i] + TEMP_SMOOTHING * current_temp


def single_physics_step(dt):
    """Führt einen kleinen Zeitschritt mit symplektischem Euler-Verfahren aus."""
    compute_forces()

    for i in range(NODE_COUNT):
        vx[i] += ax[i] * dt
        vy[i] += ay[i] * dt
        x[i] += vx[i] * dt
        y[i] += vy[i] * dt

    scatter_velocity_directions()
    apply_boundary_thermostats()
    update_temperature_smoothing()

    
def advance_simulation(visual_steps=1):
    """Lässt die Simulation mehrere kleine Zeitschritte laufen."""
    speed = float_value("speed_slider", 1.0)

    # Geschwindigkeit wird über die Anzahl stabiler Teilzeitschritte gesteuert,
    # nicht über einen viel größeren dt. Das reduziert numerische Instabilität.
    substeps_per_visual_step = max(1, int(round(3 * speed)))

    for _ in range(visual_steps * substeps_per_visual_step):
        single_physics_step(BASE_DT)


# ---------------------------------------------------------------------------
# Auswertung für Diagramm und Messwerte
# ---------------------------------------------------------------------------


def column_average_temperatures():
    """Mittlere Modelltemperatur jeder Spalte."""
    values = []
    for col in range(N):
        total = 0.0
        for row in range(N):
            total += temp_smooth[idx(col, row)]
        values.append(total / N)
    return values


def mean_model_temperature():
    """Mittlere Modelltemperatur aller Knoten aus aktueller Bewegungsenergie."""
    total = 0.0
    for i in range(NODE_COUNT):
        total += current_node_temperature(i)
    return total / NODE_COUNT

def update_diagnostics():
    """Berechnet Diagrammwerte und Energiewerte.

    Diese Funktion wird nur alle paar Frames aufgerufen.
    Dadurch sparen wir Rechenzeit und teure DOM-Aktualisierungen.
    """
    global cached_profile_values, cached_node_energies, cached_mean_temp, cached_delta_temp
    global last_kinetic_energy, last_spring_energy, last_total_energy

    column_temps = column_average_temperatures()
    cached_mean_temp = mean_model_temperature()
    cached_delta_temp = max(column_temps) - min(column_temps)

    # Gesamtenergie pro Spalte: kinetische Energie + zugeordnete Federenergie.
    cached_profile_values = [0.0 for _ in range(N)]
    cached_node_energies = [0.0 for _ in range(NODE_COUNT)]
    kinetic = 0.0
    for i in range(NODE_COUNT):
        node_energy = 0.5 * MASS * (vx[i] * vx[i] + vy[i] * vy[i])
        kinetic += node_energy
        cached_node_energies[i] = node_energy
        cached_profile_values[i % N] += node_energy

    spring = compute_spring_energy_only(cached_profile_values, cached_node_energies)

    last_kinetic_energy = kinetic
    last_spring_energy = spring
    last_total_energy = kinetic + spring


# ---------------------------------------------------------------------------
# Zeichnen: Simulation, Energiefarben und Diagramm
# ---------------------------------------------------------------------------


def energy_color(energy):
    """Farbskala für die lokale Gesamtenergie (kinetisch + potenziell).

    Blau = wenig, hell = mittel, orange/rot = viel Energie.
    Die feste Skala ist auf ENERGY_COLOR_REFERENCE begrenzt.
    """
    t = clamp(energy / ENERGY_COLOR_REFERENCE, 0.0, 1.0)

    cold = (45, 100, 220)
    mid = (240, 246, 255)
    hot = (230, 80, 25)

    if t < 0.5:
        u = t / 0.5
        r = int(lerp(cold[0], mid[0], u))
        g = int(lerp(cold[1], mid[1], u))
        b = int(lerp(cold[2], mid[2], u))
    else:
        u = (t - 0.5) / 0.5
        r = int(lerp(mid[0], hot[0], u))
        g = int(lerp(mid[1], hot[1], u))
        b = int(lerp(mid[2], hot[2], u))

    return f"rgb({r},{g},{b})"



def clear_canvas(ctx, canvas):
    """Canvas leeren."""
    ctx.clearRect(0, 0, canvas.width, canvas.height)


def draw_simulation():
    """Zeichnet das Feder-Masse-Gitter."""
    clear_canvas(sim_ctx, sim_canvas)

    # Vorgerechnetes Hintergrundgitter kopieren.
    sim_ctx.drawImage(background_canvas, 0, 0)

    left, top, scale = screen_geometry()

    draw_springs(left, top, scale)
    draw_nodes(left, top, scale)
    draw_simulation_labels()


def draw_springs(left, top, scale):
    """Zeichnet alle sichtbaren Nachbarfedern als einen gemeinsamen Pfad."""
    sim_ctx.save()
    sim_ctx.strokeStyle = "rgba(60, 75, 100, 0.35)"
    sim_ctx.lineWidth = 1.3
    sim_ctx.beginPath()

    for a, b in spring_pairs:
        ax_screen, ay_screen = screen_position_with_geometry(a, left, top, scale)
        bx_screen, by_screen = screen_position_with_geometry(b, left, top, scale)

        sim_ctx.moveTo(ax_screen, ay_screen)
        sim_ctx.lineTo(bx_screen, by_screen)

    sim_ctx.stroke()
    sim_ctx.restore()


def draw_nodes(left, top, scale):
    """Zeichnet alle Knoten mit Farben nach ihrer lokalen Gesamtenergie."""
    for row in range(N):
        for col in range(N):
            i = idx(col, row)
            sx, sy = screen_position_with_geometry(i, left, top, scale)
            energy = cached_node_energies[i]
            radius = 7.5

            # Randspalten etwas stärker umrahmen, weil sie im Anfangszustand
            # separat eingestellt und optional als Wärmebad festgehalten werden.
            border_width = 2.3 if col == 0 or col == N - 1 else 1.2
            border_color = "rgba(30, 40, 70, 0.75)" if col == 0 or col == N - 1 else "rgba(30, 40, 70, 0.45)"

            sim_ctx.beginPath()
            sim_ctx.arc(sx, sy, radius, 0, 2 * pi)
            sim_ctx.fillStyle = energy_color(energy)
            sim_ctx.fill()
            sim_ctx.lineWidth = border_width
            sim_ctx.strokeStyle = border_color
            sim_ctx.stroke()


def draw_simulation_labels():
    """Kleine Beschriftungen direkt im Simulationscanvas."""
    sim_ctx.save()
    sim_ctx.fillStyle = "rgba(29, 36, 51, 0.78)"
    sim_ctx.font = "14px system-ui, sans-serif"

    if is_checked("thermostat_checkbox", False):
        sim_ctx.fillStyle = "rgba(194, 65, 12, 0.95)"
        sim_ctx.fillText("Wärmebäder: Randtemperaturen konstant", 26, 58)
    else:
        sim_ctx.fillStyle = "rgba(47, 109, 246, 0.95)"
        sim_ctx.fillText("Abgeschlossenes Gitter: Energie näherungsweise erhalten", 26, 58)
    sim_ctx.restore()


def draw_profile():
    """Zeichnet die Gesamtenergie pro Spalte über die 10 Spalten."""
    clear_canvas(profile_ctx, profile_canvas)

    values = cached_profile_values
    width = profile_canvas.width
    height = profile_canvas.height
    margin_left = 54
    margin_right = 26
    margin_top = 24
    margin_bottom = 42
    plot_w = width - margin_left - margin_right
    plot_h = height - margin_top - margin_bottom

    max_energy = max(1.0, max(values) * 1.15)

    # Achsen und Hilfslinien
    profile_ctx.save()
    profile_ctx.strokeStyle = "rgba(120, 135, 160, 0.25)"
    profile_ctx.lineWidth = 1
    profile_ctx.beginPath()
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        y_grid = margin_top + plot_h * (1.0 - frac)
        profile_ctx.moveTo(margin_left, y_grid)
        profile_ctx.lineTo(margin_left + plot_w, y_grid)
    profile_ctx.stroke()

    profile_ctx.strokeStyle = "rgba(30, 40, 70, 0.55)"
    profile_ctx.beginPath()
    profile_ctx.moveTo(margin_left, margin_top)
    profile_ctx.lineTo(margin_left, margin_top + plot_h)
    profile_ctx.lineTo(margin_left + plot_w, margin_top + plot_h)
    profile_ctx.stroke()

    # Profil-Linie
    points = []
    for col, energy in enumerate(values):
        x_plot = margin_left + plot_w * col / (N - 1)
        y_plot = margin_top + plot_h * (1.0 - clamp(energy / max_energy, 0.0, 1.0))
        points.append((x_plot, y_plot))

    profile_ctx.strokeStyle = "#2f6df6"
    profile_ctx.lineWidth = 2.4
    profile_ctx.beginPath()
    for p, (xp, yp) in enumerate(points):
        if p == 0:
            profile_ctx.moveTo(xp, yp)
        else:
            profile_ctx.lineTo(xp, yp)
    profile_ctx.stroke()

    for (xp, yp), energy in zip(points, values):
        profile_ctx.beginPath()
        profile_ctx.arc(xp, yp, 5.5, 0, 2 * pi)
        # Farbe basiert auf der mittleren Gesamtenergie pro Knoten dieser Spalte.
        profile_ctx.fillStyle = energy_color(energy / N)
        profile_ctx.fill()
        profile_ctx.strokeStyle = "rgba(30, 40, 70, 0.55)"
        profile_ctx.lineWidth = 1
        profile_ctx.stroke()

    # Beschriftungen
    profile_ctx.fillStyle = "#657086"
    profile_ctx.font = "13px system-ui, sans-serif"
    profile_ctx.fillText("Spalte", width / 2 - 18, height - 9)
    profile_ctx.fillText("E", 20, margin_top - 9)
    profile_ctx.fillText(f"{max_energy:.1f}", 10, margin_top + 5)
    profile_ctx.fillText("0", 35, margin_top + plot_h + 5)
    profile_ctx.fillText("1", margin_left - 3, height - 19)
    profile_ctx.fillText(str(N), margin_left + plot_w - 8, height - 19)
    profile_ctx.restore()


def draw_all(force_profile=False):
    """Aktualisiert die Darstellungen.

    Die Simulation wird regelmäßig gezeichnet.
    Das Diagramm wird nur bei Bedarf neu gezeichnet.
    """
    draw_simulation()

    if force_profile:
        draw_profile()


# ---------------------------------------------------------------------------
# UI-Anzeigen aktualisieren
# ---------------------------------------------------------------------------


def update_slider_labels_only():
    """Aktualisiert nur Sliderwerte und Buttonstatus."""
    set_text("speed_value", f"{float_value('speed_slider', 1.0):.2f}×")
    set_text("stiffness_value", f"{float_value('stiffness_slider', 5.0):.2f}")
    set_text("temp_left_value", f"{int_value('temp_left_slider', 100)}")
    set_text("temp_middle_value", f"{int_value('temp_middle_slider', 20)}")
    set_text("temp_right_value", f"{int_value('temp_right_slider', 20)}")

    set_text("status_text", "läuft" if is_running else "Pause")
    set_text("play_button", "⏸ Pause" if is_running else "▶ Start")


def update_labels_and_stats():
    """Zahlenanzeigen, Buttontexte und Messwerte aktualisieren.

    Diese Funktion wird im Animationsbetrieb nur alle paar Frames aufgerufen.
    """
    update_slider_labels_only()

    set_text("mean_temp_value", f"{cached_mean_temp:.1f}")
    set_text("delta_temp_value", f"{cached_delta_temp:.1f}")
    set_text("kin_energy_value", f"{last_kinetic_energy:.3f}")
    set_text("spring_energy_value", f"{last_spring_energy:.3f}")
    set_text("total_energy_value", f"{last_total_energy:.3f}")

    if initial_total_energy > 1e-12:
        drift = 100.0 * (last_total_energy - initial_total_energy) / initial_total_energy
        set_text("energy_drift_value", f"{drift:+.2f} %")
    else:
        set_text("energy_drift_value", "–")


# ---------------------------------------------------------------------------
# Event-Handler
# ---------------------------------------------------------------------------


def toggle_play(event=None):
    """Startet oder pausiert die Animation."""
    global is_running, last_timestamp, frame_counter
    is_running = not is_running
    last_timestamp = None
    update_slider_labels_only()


def reset_simulation(event=None):
    """Setzt das Gitter mit den aktuellen Temperatur-Slidern neu auf."""
    global is_running, last_timestamp, frame_counter
    is_running = False
    last_timestamp = None
    frame_counter = 0
    initialize_lattice()


def on_input(event=None):
    """Allgemeine Reaktion auf Slider/Checkboxen."""
    update_diagnostics()
    update_labels_and_stats()
    draw_all(force_profile=True)


def on_temperature_input(event=None):
    """Temperaturslider ändern den Anfangszustand.

    Wenn die Simulation pausiert ist, wird das Gitter sofort neu initialisiert.
    Während die Simulation läuft, ändern sie nur die Zielwerte für ein aktives
    Wärmebad; der Reset-Button übernimmt sie wieder als Anfangszustand.
    """
    if not is_running:
        initialize_lattice()
    else:
        update_slider_labels_only()


def on_stiffness_input(event=None):
    """Kopplungsstärke ändern und Energiereferenz sinnvoll aktualisieren."""
    global initial_total_energy

    update_diagnostics()

    if not is_running:
        initial_total_energy = last_total_energy

    update_labels_and_stats()
    draw_all(force_profile=True)


def animation_loop(timestamp):
    """Haupt-Animationsschleife. Wird mit requestAnimationFrame aufgerufen."""
    global last_timestamp, frame_counter

    if is_running:
        advance_simulation(visual_steps=1)
        frame_counter += 1

        if frame_counter % DIAGNOSTIC_UPDATE_INTERVAL == 0:
            update_diagnostics()
            update_labels_and_stats()
            draw_all(force_profile=True)
        else:
            draw_all(force_profile=False)

    last_timestamp = timestamp
    window.requestAnimationFrame(animation_loop_proxy)


def add_event(element_id, event_name, handler):
    """EventListener hinzufügen und Proxy speichern."""
    element = el(element_id)
    if element is None:
        return
    proxy = create_proxy(handler)
    _proxies.append(proxy)
    element.addEventListener(event_name, proxy)


# ---------------------------------------------------------------------------
# App starten
# ---------------------------------------------------------------------------


# Proxies/EventListener registrieren.
build_spring_pairs()
render_background_grid()
add_event("play_button", "click", toggle_play)
add_event("reset_button", "click", reset_simulation)
add_event("speed_slider", "input", on_input)

for slider_id in (
    "temp_left_slider",
    "temp_middle_slider",
    "temp_right_slider",
):
    add_event(slider_id, "input", on_temperature_input)

add_event("stiffness_slider", "input", on_stiffness_input)
add_event("thermostat_checkbox", "change", on_input)

# Anfangszustand aufbauen und zeichnen.
initialize_lattice()

# Animationsloop starten.
animation_loop_proxy = create_proxy(animation_loop)
_proxies.append(animation_loop_proxy)
window.requestAnimationFrame(animation_loop_proxy)
