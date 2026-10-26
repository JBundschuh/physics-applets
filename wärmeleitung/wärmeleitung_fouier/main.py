"""
Temperaturfeld-Wärmeleitung: vereinfachtes Fourier-Modell
=========================================================n
Dieses Applet stellt vereinfach die 1D-Wächmeleitung dar.

Physikidee
----------
Die Temperatur wird nicht aus einer mechanischen Bewegung berechnet.
Stattdessen besitzt jede Spalte des Gitters einen Temperaturwert T[i].
Diese Werte entwickeln sich nach einer diskreten 1D-Wärmeleitungsgleichung.

Für innere Spalten gilt näherungsweise:

    T_neu[i] = T[i] + a * (T[i-1] - 2*T[i] + T[i+1])

Im Code wird die gleiche Idee als paarweiser Austausch zwischen
Nachbarspalten umgesetzt. Das ist besonders anschaulich und erhält im
abgeschlossenen System die Gesamtwärme exakt bis auf Rundungsfehler.

Darstellungsidee
----------------
Das sichtbare 2D-Gitter ist nur eine Visualisierung. Alle Knoten in derselben
Spalte verwenden denselben Temperaturwert. Heiße Spalten werden rot/orange
gezeichnet und zittern stärker. Kalte Spalten werden blau dargestellt und
zittern weniger stark.

Wichtig für die Didaktik:
Das Zittern verursacht in diesem Applet nicht die Wärmeleitung. Es zeigt nur
modellhaft die Vorstellung: höhere Temperatur entspricht stärkerer thermischer
Bewegung.
"""

from math import sqrt, sin, cos, pi
from random import random
from js import document, window
from pyodide.ffi import create_proxy


# ---------------------------------------------------------------------------
# Robuste DOM-Hilfsfunktionen
# ---------------------------------------------------------------------------


def el(element_id):
    """HTML-Element per id holen.

    Pyodide kann JavaScript-null als eigenes JsNull-Objekt liefern.
    Deshalb prüfen wir zusätzlich auf JsNull/JsUndefined.
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
    """Sliderwert als float lesen."""
    element = el(element_id)
    if element is None:
        return default
    return float(element.value)


def int_value(element_id, default=0):
    """Sliderwert als int lesen."""
    element = el(element_id)
    if element is None:
        return default
    return int(float(element.value))


def is_checked(element_id, default=False):
    """Checkboxzustand lesen."""
    element = el(element_id)
    if element is None:
        return default
    return bool(element.checked)


def set_text(element_id, text):
    """Text eines Elements setzen, falls es existiert."""
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

# Gitterdarstellung: 10 Spalten x 10 Reihen.
# Temperatur wird 1D berechnet: ein Temperaturwert pro Spalte.
COLS = 10
ROWS = 10
NODE_COUNT = COLS * ROWS

# Temperaturwerte pro Spalte.
T = []
T_initial_sum = 0.0

# Faktor für die visualisierte thermische Bewegung (kein Modellparameter).
JITTER_STRENGTH = 1.0

# Phasen/Frequenzen für die visuelle thermische Bewegung der Knoten.
# Diese Werte haben keinen Einfluss auf die Wärmeleitung.
phase_x = []
phase_y = []
freq_x = []
freq_y = []

# Animation
is_running = False
frame_counter = 0
simulation_time = 0.0
_proxies = []


# ---------------------------------------------------------------------------
# Mathematische Hilfsfunktionen
# ---------------------------------------------------------------------------


def clamp(value, low, high):
    """Wert auf ein Intervall begrenzen."""
    return max(low, min(high, value))


def lerp(a, b, t):
    """Lineare Interpolation."""
    return a + (b - a) * t


def idx(col, row):
    """2D-Gitterindex in linearen Index umwandeln."""
    return row * COLS + col


def temperature_color(temp):
    """Farbskala: blau = kalt, hell = mittel, orange/rot = heiß."""
    t = clamp(temp / 120.0, 0.0, 1.0)

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


def temperature_to_jitter_amplitude(temp):
    """Temperatur in sichtbare Zitteramplitude umrechnen.

    Die Wurzel macht die Darstellung etwas ruhiger: sehr hohe Temperaturen
    werden nicht überproportional stark vergrößert.
    """
    return JITTER_STRENGTH * 7.5 * sqrt(max(0.0, temp) / 120.0)


# ---------------------------------------------------------------------------
# Initialisierung und Wärmeleitung
# ---------------------------------------------------------------------------


def target_temperature_for_column(col):
    """Starttemperatur je nach Spalte."""
    if col == 0:
        return float_value("temp_left_slider", 100.0)
    if col == COLS - 1:
        return float_value("temp_right_slider", 20.0)
    return float_value("temp_middle_slider", 20.0)


def initialize_model():
    """Temperaturfeld und visuelle Bewegungsphasen neu initialisieren."""
    global T, T_initial_sum, phase_x, phase_y, freq_x, freq_y
    global simulation_time, frame_counter

    T = []
    for col in range(COLS):
        T.append(target_temperature_for_column(col))

    T_initial_sum = sum(T)

    phase_x = []
    phase_y = []
    freq_x = []
    freq_y = []

    for _ in range(NODE_COUNT):
        phase_x.append(2.0 * pi * random())
        phase_y.append(2.0 * pi * random())
        freq_x.append(1.2 + 2.8 * random())
        freq_y.append(1.2 + 2.8 * random())

    simulation_time = 0.0
    frame_counter = 0

    update_labels_and_stats()
    draw_all()


def heat_exchange_step():
    """Ein diskreter Wärmeleitungsschritt.

    Das Modell arbeitet mit paarweisem Austausch zwischen Nachbarspalten:

        warm -> kalt

    Wenn keine Randtemperaturen festgehalten werden, bleibt die Summe aller
    Spaltentemperaturen erhalten. Das entspricht einem abgeschlossenen Körper.
    """
    global T

    # Austauschfaktor. Für Stabilität sollte der Wert nicht zu groß werden.
    a = float_value("diffusion_slider", 0.18)

    # Änderungen zunächst sammeln, damit alle Nachbarpaare aus demselben alten
    # Zustand berechnet werden.
    dT = [0.0 for _ in range(COLS)]

    for col in range(COLS - 1):
        # Positive Differenz bedeutet: linke Spalte ist wärmer als rechte.
        diff = T[col] - T[col + 1]

        # Ein Teil der Temperaturdifferenz wird ausgeglichen.
        transfer = a * diff

        dT[col] -= transfer
        dT[col + 1] += transfer

    for col in range(COLS):
        T[col] += dT[col]

    # Optionale Wärmebäder links/rechts.
    # Wichtig: Nur die Randspalten werden geregelt. Innen entwickelt sich frei.
    if is_checked("thermostat_checkbox", False):
        T[0] = float_value("temp_left_slider", 100.0)
        T[COLS - 1] = float_value("temp_right_slider", 20.0)


def advance_simulation():
    """Simulation um mehrere kleine Wärmeschritte weiterführen."""
    global simulation_time

    speed = float_value("speed_slider", 1.0)
    substeps = max(1, int(round(2 * speed)))

    for _ in range(substeps):
        heat_exchange_step()
        simulation_time += 0.035


# ---------------------------------------------------------------------------
# Zeichenfunktionen
# ---------------------------------------------------------------------------


def screen_geometry():
    """Geometrie des sichtbaren Gitters im Canvas."""
    width = sim_canvas.width
    height = sim_canvas.height
    margin = 74
    usable_w = width - 2 * margin
    usable_h = height - 2 * margin
    scale_x = usable_w / (COLS - 1)
    scale_y = usable_h / (ROWS - 1)
    left = margin
    top = margin
    return left, top, scale_x, scale_y


def rest_position(col, row):
    """Ruheposition eines Knotens im Canvas."""
    left, top, scale_x, scale_y = screen_geometry()
    return left + col * scale_x, top + row * scale_y


def node_position(col, row):
    """Sichtbare Position eines Knotens.

    Die Wärmeleitung nutzt nur die Temperaturwerte T[col].
    Die Bewegung hier ist eine reine Visualisierung um die Ruhelage.
    """
    sx, sy = rest_position(col, row)

    node = idx(col, row)
    amp = temperature_to_jitter_amplitude(T[col])

    # Smoothes, ungeordnet wirkendes Zittern durch zwei überlagerte Phasen.
    dx = amp * sin(phase_x[node] + freq_x[node] * simulation_time)
    dy = amp * cos(phase_y[node] + freq_y[node] * simulation_time)

    return sx + dx, sy + dy


def clear_canvas(ctx, canvas):
    """Canvas leeren."""
    ctx.clearRect(0, 0, canvas.width, canvas.height)


def draw_simulation():
    """Gitter und Knoten zeichnen."""
    clear_canvas(sim_ctx, sim_canvas)

    # Ruhiges Hintergrund-Rechteck.
    sim_ctx.save()
    sim_ctx.fillStyle = "rgba(247, 249, 252, 0.85)"
    sim_ctx.fillRect(0, 0, sim_canvas.width, sim_canvas.height)
    sim_ctx.restore()

    draw_grid_paths()

    draw_nodes()
    draw_simulation_hint()


def draw_grid_paths():
    """Verbindet die Knoten durch Linien.

    Diese Pfade sind keine mechanischen Federn. Sie dienen nur dazu, das
    Temperaturfeld als zusammenhängendes Gitter sichtbar zu machen.
    """
    sim_ctx.save()
    sim_ctx.strokeStyle = "rgba(60, 75, 100, 0.30)"
    sim_ctx.lineWidth = 1.25
    sim_ctx.beginPath()

    # Horizontale Pfade.
    for row in range(ROWS):
        for col in range(COLS - 1):
            x1, y1 = node_position(col, row)
            x2, y2 = node_position(col + 1, row)
            sim_ctx.moveTo(x1, y1)
            sim_ctx.lineTo(x2, y2)

    # Vertikale Pfade.
    for col in range(COLS):
        for row in range(ROWS - 1):
            x1, y1 = node_position(col, row)
            x2, y2 = node_position(col, row + 1)
            sim_ctx.moveTo(x1, y1)
            sim_ctx.lineTo(x2, y2)

    sim_ctx.stroke()
    sim_ctx.restore()


def draw_nodes():
    """Alle Knoten zeichnen. Farbe entspricht der Spaltentemperatur."""
    for row in range(ROWS):
        for col in range(COLS):
            sx, sy = node_position(col, row)
            temp = T[col]

            radius = 7.5
            border_width = 2.2 if col == 0 or col == COLS - 1 else 1.1
            border_color = "rgba(30, 40, 70, 0.75)" if col == 0 or col == COLS - 1 else "rgba(30, 40, 70, 0.42)"

            sim_ctx.beginPath()
            sim_ctx.arc(sx, sy, radius, 0, 2.0 * pi)
            sim_ctx.fillStyle = temperature_color(temp)
            sim_ctx.fill()
            sim_ctx.lineWidth = border_width
            sim_ctx.strokeStyle = border_color
            sim_ctx.stroke()


def draw_simulation_hint():
    """Kleiner Hinweis im Canvas."""
    sim_ctx.save()
    sim_ctx.font = "14px system-ui, sans-serif"

    if is_checked("thermostat_checkbox", False):
        sim_ctx.fillStyle = "rgba(194, 65, 12, 0.95)"
        sim_ctx.fillText("Randtemperaturen festgehalten", 26, 38)
    else:
        sim_ctx.fillStyle = "rgba(47, 109, 246, 0.95)"
        sim_ctx.fillText("Abgeschlossenes System", 26, 38)

    sim_ctx.restore()


def draw_profile():
    """Temperaturprofil entlang der x-Richtung zeichnen."""
    clear_canvas(profile_ctx, profile_canvas)

    width = profile_canvas.width
    height = profile_canvas.height
    margin_left = 54
    margin_right = 26
    margin_top = 24
    margin_bottom = 42
    plot_w = width - margin_left - margin_right
    plot_h = height - margin_top - margin_bottom

    max_temp = max(120.0, max(T) * 1.15)

    profile_ctx.save()

    # Hilfslinien bündeln: ein beginPath, ein stroke.
    profile_ctx.strokeStyle = "rgba(120, 135, 160, 0.25)"
    profile_ctx.lineWidth = 1
    profile_ctx.beginPath()
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        y_grid = margin_top + plot_h * (1.0 - frac)
        profile_ctx.moveTo(margin_left, y_grid)
        profile_ctx.lineTo(margin_left + plot_w, y_grid)
    profile_ctx.stroke()

    # Achsen.
    profile_ctx.strokeStyle = "rgba(30, 40, 70, 0.55)"
    profile_ctx.beginPath()
    profile_ctx.moveTo(margin_left, margin_top)
    profile_ctx.lineTo(margin_left, margin_top + plot_h)
    profile_ctx.lineTo(margin_left + plot_w, margin_top + plot_h)
    profile_ctx.stroke()

    # Punkte des Temperaturprofils.
    points = []
    for col, temp in enumerate(T):
        xp = margin_left + plot_w * col / (COLS - 1)
        yp = margin_top + plot_h * (1.0 - clamp(temp / max_temp, 0.0, 1.0))
        points.append((xp, yp, temp))

    # Profillinie.
    profile_ctx.strokeStyle = "#2f6df6"
    profile_ctx.lineWidth = 2.4
    profile_ctx.beginPath()
    for p, (xp, yp, _) in enumerate(points):
        if p == 0:
            profile_ctx.moveTo(xp, yp)
        else:
            profile_ctx.lineTo(xp, yp)
    profile_ctx.stroke()

    # Profilpunkte.
    for xp, yp, temp in points:
        profile_ctx.beginPath()
        profile_ctx.arc(xp, yp, 5.5, 0, 2.0 * pi)
        profile_ctx.fillStyle = temperature_color(temp)
        profile_ctx.fill()
        profile_ctx.strokeStyle = "rgba(30, 40, 70, 0.55)"
        profile_ctx.lineWidth = 1
        profile_ctx.stroke()

    profile_ctx.fillStyle = "#657086"
    profile_ctx.font = "13px system-ui, sans-serif"
    profile_ctx.fillText("Spalte", margin_left + plot_w - 42, height - 12)
    profile_ctx.fillText("T", 20, margin_top + 5)
    profile_ctx.fillText("1", margin_left - 3, height - 18)
    profile_ctx.fillText(str(COLS), margin_left + plot_w - 8, height - 18)

    profile_ctx.restore()


def draw_all():
    """Alle Canvas-Bereiche neu zeichnen."""
    draw_simulation()
    draw_profile()


# ---------------------------------------------------------------------------
# UI und Messwerte
# ---------------------------------------------------------------------------


def mean_temperature():
    """Mittlere Temperatur über alle Spalten."""
    return sum(T) / COLS


def delta_temperature():
    """Temperaturdifferenz zwischen heißester und kältester Spalte."""
    return max(T) - min(T)


def update_labels_and_stats():
    """Sliderwerte, Status und Messwerte aktualisieren."""
    set_text("speed_value", f"{float_value('speed_slider', 1.0):.2f}×")
    set_text("diffusion_value", f"{float_value('diffusion_slider', 0.18):.2f}")
    set_text("temp_left_value", f"{int_value('temp_left_slider', 100)}")
    set_text("temp_middle_value", f"{int_value('temp_middle_slider', 20)}")
    set_text("temp_right_value", f"{int_value('temp_right_slider', 20)}")

    set_text("play_button", "⏸ Pause" if is_running else "▶ Start")

    mean_T = mean_temperature() if len(T) == COLS else 0.0
    delta_T = delta_temperature() if len(T) == COLS else 0.0
    total_T = sum(T) if len(T) == COLS else 0.0

    set_text("mean_temp_value", f"{mean_T:.1f}")
    set_text("delta_temp_value", f"{delta_T:.1f}")
    set_text("total_temp_value", f"{total_T:.1f}")

    if abs(T_initial_sum) > 1e-12:
        drift = 100.0 * (total_T - T_initial_sum) / T_initial_sum
        set_text("total_drift_value", f"{drift:+.2f} %")
    else:
        set_text("total_drift_value", "–")



# ---------------------------------------------------------------------------
# Event-Handler
# ---------------------------------------------------------------------------


def toggle_play(event=None):
    """Animation starten/pausieren."""
    global is_running
    is_running = not is_running
    update_labels_and_stats()


def reset_simulation(event=None):
    """Modell mit aktuellen Startwerten neu aufbauen."""
    global is_running
    is_running = False
    initialize_model()


def on_input(event=None):
    """Modellparameter und Randbedingungen aktualisieren."""
    update_labels_and_stats()
    draw_all()


def on_temperature_input(event=None):
    """Temperaturslider verhalten sich je nach Zustand unterschiedlich.

    Im pausierten Zustand wird direkt neu initialisiert.
    Während die Simulation läuft, wirken die linken/rechten Slider nur dann
    direkt, wenn die Wärmebad-Checkbox aktiv ist. Innen bleibt nach Start frei.
    """
    if not is_running:
        initialize_model()
    else:
        update_labels_and_stats()


def animation_loop(timestamp):
    """Hauptschleife über requestAnimationFrame."""
    global frame_counter

    if is_running:
        advance_simulation()
        frame_counter += 1

        # Statistik/Labels müssen nicht zwingend in jedem Frame aktualisiert werden.
        if frame_counter % 4 == 0:
            update_labels_and_stats()

        draw_all()

    window.requestAnimationFrame(animation_loop_proxy)


def add_event(element_id, event_name, handler):
    """EventListener registrieren und Proxy speichern."""
    element = el(element_id)
    if element is None:
        return
    proxy = create_proxy(handler)
    _proxies.append(proxy)
    element.addEventListener(event_name, proxy)


# ---------------------------------------------------------------------------
# App starten
# ---------------------------------------------------------------------------


add_event("play_button", "click", toggle_play)
add_event("reset_button", "click", reset_simulation)

for slider_id in (
    "speed_slider",
    "diffusion_slider",
):
    add_event(slider_id, "input", on_input)

for slider_id in (
    "temp_left_slider",
    "temp_middle_slider",
    "temp_right_slider",
):
    add_event(slider_id, "input", on_temperature_input)

add_event("thermostat_checkbox", "change", on_input)

initialize_model()

animation_loop_proxy = create_proxy(animation_loop)
_proxies.append(animation_loop_proxy)
window.requestAnimationFrame(animation_loop_proxy)
