"""
Überlagerung stehender Wellen
=============================

Dieses Applet ist bewusst einfach aufgebaut:

1. Es gibt keine numerische Simulation.
   Die Positionen der Knoten werden direkt aus Sinusfunktionen berechnet.

2. Die 1D-Darstellung beschreibt eine Saite mit festen Enden.
   Die zulässigen Eigenmoden sind Vielfache einer halben Wellenlänge.

3. Die 2D-Darstellung beschreibt ein ebenes Gitter mit festen Rändern.
   Die inneren Massen können in x- und/oder y-Richtung ausgelenkt werden.
   Es wird keine z-Achse eingeführt.

4. Die 2D-Bedienung folgt bewusst einem einfachen didaktischen Prinzip:
   Jede Mode (m,n) wird durch ein Kästchen in einer Modenmatrix dargestellt.
   Klick auf ein Kästchen: Mode ein/aus.
   Dadurch muss der Nutzer nicht viele Amplituden-Slider bedienen.

5. Für gute PyScript-Kompatibilität wird nur Standard-Python verwendet.
   Es werden keine externen Pakete wie NumPy benötigt.
"""

from math import sin, cos, pi, sqrt
from js import document, window
from pyodide.ffi import create_proxy


# ---------------------------------------------------------------------------
# Kleine Hilfsfunktionen für den DOM-Zugriff
# ---------------------------------------------------------------------------


def el(element_id):
    """
    Holt ein HTML-Element über seine id.

    Wichtig für PyScript/Pyodide:
    Wird ein Element nicht gefunden, kommt aus JavaScript eigentlich `null`.
    In Pyodide kann dieses `null` aber als spezielles Objekt vom Typ JsNull
    erscheinen. Dieses Objekt ist nicht dasselbe wie Python-None.

    Deshalb prüfen wir hier robust auf None, JsNull und JsUndefined.
    Alle anderen Funktionen können danach sicher mit `if element is not None`
    arbeiten.
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
    """Liest den Wert eines Sliders als float."""
    element = el(element_id)
    if element is None:
        return default
    return float(element.value)


def int_value(element_id, default=0):
    """Liest den Wert eines Sliders als int."""
    element = el(element_id)
    if element is None:
        return default
    return int(float(element.value))


def is_checked(element_id, default=False):
    """Liest den Zustand einer Checkbox."""
    element = el(element_id)
    if element is None:
        return default
    return bool(element.checked)


def set_text(element_id, text):
    """Setzt Textinhalt eines HTML-Elements, falls es existiert."""
    element = el(element_id)
    if element is not None:
        element.textContent = text


def set_html(element_id, html):
    """Setzt HTML-Inhalt eines HTML-Elements, falls es existiert."""
    element = el(element_id)
    if element is not None:
        element.innerHTML = html


# ---------------------------------------------------------------------------
# Globale App-Zustände
# ---------------------------------------------------------------------------

canvas = el("sim_canvas")
ctx = canvas.getContext("2d")

# Die Phase entspricht dem Grundwinkel omega_1 * t.
# phase = 0 bedeutet: alle Kosinus-Terme sind am Anfang maximal.
phase = 0.0

# Animationsstatus
is_running = False
last_timestamp = None

# Proxies müssen gespeichert werden, damit Pyodide sie nicht aus dem Speicher entfernt.
_proxies = []

# 1D-Amplituden: A_n für n = 1 bis 5.
# Start: nur die Grundmode ist sichtbar angeregt.
amplitudes_1d = {
    1: 0.65,
    2: 0.0,
    3: 0.0,
    4: 0.0,
    5: 0.0,
}

# 2D-Moden: True bedeutet, die Mode (m,n) ist eingeschaltet.
# Die maximale Matrixgröße ist 5 x 5. Angezeigt wird nur der Bereich,
# den der Nutzer über den Slider „innere Massen / Moden pro Richtung“ wählt.
MAX_2D_MODES = 5
active_modes_2d = {}
for m in range(1, MAX_2D_MODES + 1):
    for n in range(1, MAX_2D_MODES + 1):
        active_modes_2d[(m, n)] = False

# Start: Grundmode (1,1) eingeschaltet.
active_modes_2d[(1, 1)] = True


# ---------------------------------------------------------------------------
# Dynamische Bedienelemente erzeugen
# ---------------------------------------------------------------------------


def read_current_1d_amplitudes():
    """Speichert aktuelle 1D-Sliderwerte, bevor die Slider neu aufgebaut werden."""
    for n in range(1, 6):
        slider = el(f"amp_1d_{n}")
        if slider is not None:
            amplitudes_1d[n] = float(slider.value)


def build_1d_amplitude_controls():
    """Erzeugt die Amplituden-Slider für die 1D-Moden."""
    container = el("amplitude_controls_1d")
    if container is None:
        return

    container.innerHTML = ""
    active_modes = int_value("active_modes_1d_slider", 3)

    for n in range(1, active_modes + 1):
        item = document.createElement("div")
        item.className = "amplitude-item"
        item.innerHTML = f"""
            <label class="slider-label" for="amp_1d_{n}">
              <span>Amplitude A<sub>{n}</sub></span>
              <output id="amp_1d_{n}_value">{amplitudes_1d[n]:+.2f}</output>
            </label>
            <input id="amp_1d_{n}" type="range" min="-1" max="1" step="0.05" value="{amplitudes_1d[n]}" />
            <p class="microcopy">Mode {n}: {n} halbe Wellenlänge(n) zwischen den festen Enden.</p>
        """
        container.appendChild(item)

        slider = el(f"amp_1d_{n}")
        if slider is not None:
            slider.addEventListener("input", on_input_proxy)


def build_2d_mode_matrix_controls():
    """
    Erzeugt die anklickbare Modenmatrix für die 2D-Gitterschwingung.

    Beispiel:
    Bei 3 x 3 inneren Massen gibt es 3 x 3 mögliche Moden.
    Das Kästchen (m,n) schaltet die Mode

        sin(m*pi*x/Lx) * sin(n*pi*y/Ly)

    ein oder aus.
    """
    container = el("mode_matrix_2d")
    if container is None:
        return

    mode_count = int_value("mode_count_2d_slider", 3)
    container.innerHTML = ""
    container.style.gridTemplateColumns = f"repeat({mode_count}, minmax(0, 1fr))"

    # Zeilen entsprechen n, Spalten entsprechen m.
    # Das ist bewusst wie eine kleine Matrix angeordnet.
    for n in range(1, mode_count + 1):
        for m in range(1, mode_count + 1):
            button = document.createElement("button")
            button.className = "mode-cell"
            if active_modes_2d[(m, n)]:
                button.classList.add("active")

            button.setAttribute("type", "button")
            button.setAttribute("data-m", str(m))
            button.setAttribute("data-n", str(n))
            button.setAttribute("aria-pressed", "true" if active_modes_2d[(m, n)] else "false")
            button.innerHTML = f"""
                <span class="mode-cell-title">({m},{n})</span>
                <span class="mode-cell-sub">m={m}, n={n}</span>
            """
            button.addEventListener("click", on_toggle_2d_mode_proxy)
            container.appendChild(button)


# ---------------------------------------------------------------------------
# UI aktualisieren
# ---------------------------------------------------------------------------


def update_labels():
    """Aktualisiert alle Zahlenanzeigen neben den Slidern."""
    set_text("speed_value", f"{float_value('speed_slider', 1.0):.2f}×")
    set_text("phase_value", f"{int_value('phase_slider', 0)}°")

    set_text("elements_1d_value", str(int_value("elements_1d_slider", 24)))
    set_text("active_modes_1d_value", str(int_value("active_modes_1d_slider", 3)))

    mode_count = int_value("mode_count_2d_slider", 3)
    set_text("mode_count_2d_value", f"{mode_count} × {mode_count}")
    set_text("displacement_scale_2d_value", f"{float_value('displacement_scale_2d_slider', 1.0):.2f}×")

    # Dynamisch erzeugte 1D-Amplitudenanzeigen
    for n in range(1, 6):
        slider = el(f"amp_1d_{n}")
        label = el(f"amp_1d_{n}_value")
        if slider is not None and label is not None:
            label.textContent = f"{float(slider.value):+.2f}"

    # Anzahl der aktiven 2D-Moden anzeigen.
    active_count = 0
    for m in range(1, mode_count + 1):
        for n in range(1, mode_count + 1):
            if active_modes_2d[(m, n)]:
                active_count += 1
    set_text("active_modes_2d_value", str(active_count))


def update_formula_text():
    """Zeigt die passende Modellgleichung für 1D oder 2D an."""
    model = el("model_select")
    if model is not None and model.value == "1d":
        set_html("formula_text", """
            <p>Für die Saite mit festen Enden gilt:</p>
            <code>y(x,t) = Σ Aₙ · sin(nπx/L) · cos(ωₙt)</code>
            <p>Nur ganzzahlige Vielfache der halben Wellenlänge erfüllen die Randbedingung y = 0 an beiden Enden.</p>
            <p>Bei aktivierter physikalischer Frequenz gilt: ωₙ = n · ω₁.</p>
        """)
    else:
        set_html("formula_text", """
            <p>Für das ebene Gitter werden innere Massen innerhalb der x-y-Ebene verschoben:</p>
            <code>x' = x + u(x,y,t)<br>y' = y + v(x,y,t)</code>
            <code>Form der Mode (m,n): sin(mπx/Lₓ) · sin(nπy/Lᵧ)</code>
            <p>Ein Kästchen in der Modenmatrix schaltet genau eine Mode (m,n) ein oder aus.</p>
            <p>Die Sinus-Terme verschwinden an den festen Rändern. Deshalb bleiben die Randpunkte unverformt.</p>
        """)


def update_visible_controls():
    """Blendet je nach Modus die passenden Kontrollelemente ein."""
    model = el("model_select")
    if model is not None and model.value == "1d":
        el("controls_1d").classList.remove("hidden")
        el("controls_2d").classList.add("hidden")
        set_text("view_title", "1D-Saite mit festen Enden")
        set_text("view_hint", "Diskrete Knoten, gerade Verbindungslinien.")
    else:
        el("controls_1d").classList.add("hidden")
        el("controls_2d").classList.remove("hidden")
        set_text("view_title", "2D-Gitterschwingung mit festen Rändern")
        set_text("view_hint", "Modenmatrix: Kästchen klicken, um Eigenmoden ein- oder auszuschalten.")

    update_formula_text()


# ---------------------------------------------------------------------------
# Physikalische Modellfunktionen
# ---------------------------------------------------------------------------


def frequency_factor_1d(n):
    """
    Frequenzfaktor für die n-te 1D-Mode.

    Physikalische Variante:
        omega_n = n * omega_1

    Vereinfachte Variante:
        alle Moden verwenden omega_1
    """
    if is_checked("physical_frequency_checkbox", True):
        return n
    return 1


def frequency_factor_2d(m, n):
    """
    Frequenzfaktor für eine 2D-Mode.

    Für ein einfaches rechteckiges Gitterschema wählen wir als didaktische
    Näherung einen Faktor proportional zu sqrt(m²+n²).
    Durch Division durch sqrt(2) bekommt die Grundmode (1,1) den Faktor 1.
    """
    if is_checked("physical_frequency_checkbox", True):
        return sqrt(m * m + n * n) / sqrt(2)
    return 1


def displacement_1d(x_norm, current_phase):
    """
    Berechnet die gesamte 1D-Auslenkung an einer normierten Position x_norm.

    x_norm liegt zwischen 0 und 1.
    An x_norm = 0 und x_norm = 1 ist sin(n*pi*x_norm) immer 0.
    Dadurch bleiben die Enden fest.
    """
    active_modes = int_value("active_modes_1d_slider", 3)
    y = 0.0
    for n in range(1, active_modes + 1):
        amp = amplitudes_1d[n]
        shape = sin(n * pi * x_norm)
        time_part = cos(frequency_factor_1d(n) * current_phase)
        y += amp * shape * time_part
    return y


def displacement_1d_single_mode(x_norm, current_phase, n):
    """Berechnet nur den Beitrag einer einzelnen 1D-Mode."""
    amp = amplitudes_1d[n]
    return amp * sin(n * pi * x_norm) * cos(frequency_factor_1d(n) * current_phase)


def direction_vector_2d():
    """
    Bestimmt die globale Schwingungsrichtung für die 2D-Massen.

    Die Mode selbst liefert nur einen skalaren Formfaktor.
    Dieser Formfaktor wird dann in eine Richtung innerhalb der Zeichenebene
    umgesetzt. Dadurch bleibt die Bedienung einfach: Die Moden werden per
    Matrix ein-/ausgeschaltet, die Richtung gilt global.
    """
    selector = el("direction_2d_select")
    direction = selector.value if selector is not None else "y"

    if direction == "x":
        return 1.0, 0.0
    if direction == "diagonal":
        # Normiert, damit die diagonale Bewegung nicht sichtbar größer wird.
        return 1 / sqrt(2), 1 / sqrt(2)

    # Default: y-Richtung
    return 0.0, 1.0


def displacement_2d(u, v, current_phase, single_mode=None):
    """
    Berechnet die in-plane-Auslenkung eines 2D-Gitterpunktes.

    u, v sind normierte Koordinaten im Bereich 0..1.
    Rückgabe: dx, dy als dimensionslose Werte.

    single_mode = None:
        Überlagerung aller eingeschalteten Moden.

    single_mode = (m,n):
        Nur diese eine Mode wird berechnet. Das wird für die transparente
        Hintergrunddarstellung einzelner Moden genutzt.
    """
    mode_count = int_value("mode_count_2d_slider", 3)
    dir_x, dir_y = direction_vector_2d()
    dx = 0.0
    dy = 0.0

    for m in range(1, mode_count + 1):
        for n in range(1, mode_count + 1):
            if single_mode is None:
                if not active_modes_2d[(m, n)]:
                    continue
            else:
                if (m, n) != single_mode:
                    continue

            shape = sin(m * pi * u) * sin(n * pi * v)
            time_part = cos(frequency_factor_2d(m, n) * current_phase)
            contribution = shape * time_part
            dx += dir_x * contribution
            dy += dir_y * contribution

    return dx, dy


# ---------------------------------------------------------------------------
# Zeichenfunktionen
# ---------------------------------------------------------------------------


def clear_canvas():
    """Leert die Zeichenfläche."""
    ctx.clearRect(0, 0, canvas.width, canvas.height)


def draw_wall_support(x, y, side="left"):
    """
    Zeichnet ein einfaches Festlager-/Wandsymbol.

    side = "left" oder "right" bestimmt, auf welcher Seite die Schraffur liegt.
    """
    ctx.save()
    ctx.strokeStyle = "#334155"
    ctx.lineWidth = 2

    # Wandlinie
    ctx.beginPath()
    ctx.moveTo(x, y - 55)
    ctx.lineTo(x, y + 55)
    ctx.stroke()

    # Kleine Schraffuren
    direction = -1 if side == "left" else 1
    for k in range(-4, 5):
        yy = y + k * 12
        ctx.beginPath()
        ctx.moveTo(x, yy)
        ctx.lineTo(x + direction * 14, yy + 8)
        ctx.stroke()

    ctx.restore()


def draw_polyline(points, color="#1d4ed8", width=2, alpha=1.0):
    """Zeichnet gerade Verbindungslinien zwischen diskreten Punkten."""
    if len(points) < 2:
        return

    ctx.save()
    ctx.globalAlpha = alpha
    ctx.strokeStyle = color
    ctx.lineWidth = width
    ctx.beginPath()
    ctx.moveTo(points[0][0], points[0][1])
    for x, y in points[1:]:
        ctx.lineTo(x, y)
    ctx.stroke()
    ctx.restore()


def draw_points(points, radius=4, color="#1d4ed8", alpha=1.0):
    """Zeichnet die diskreten Knoten/Massen als kleine Kreise."""
    ctx.save()
    ctx.globalAlpha = alpha
    ctx.fillStyle = color
    for x, y in points:
        ctx.beginPath()
        ctx.arc(x, y, radius, 0, 2 * pi)
        ctx.fill()
    ctx.restore()


def draw_1d():
    """Zeichnet die 1D-Saite."""
    clear_canvas()

    width = canvas.width
    height = canvas.height

    left = 100
    right = width - 100
    length = right - left
    middle_y = height / 2

    # Skalenfaktor für die sichtbare Auslenkung.
    y_scale = 110

    elements = int_value("elements_1d_slider", 24)
    active_modes = int_value("active_modes_1d_slider", 3)
    show_modes = is_checked("show_modes_checkbox", True)

    # Ruhelage der Saite
    ctx.save()
    ctx.strokeStyle = "#cbd5e1"
    ctx.lineWidth = 1
    ctx.beginPath()
    ctx.moveTo(left, middle_y)
    ctx.lineTo(right, middle_y)
    ctx.stroke()
    ctx.restore()

    # Einzelmoden transparent im Hintergrund
    if show_modes:
        for n in range(1, active_modes + 1):
            if abs(amplitudes_1d[n]) < 0.001:
                continue
            mode_points = []
            for i in range(elements + 1):
                x_norm = i / elements
                x = left + x_norm * length
                y = middle_y - y_scale * displacement_1d_single_mode(x_norm, phase, n)
                mode_points.append((x, y))
            draw_polyline(mode_points, color="#64748b", width=1.5, alpha=0.28)

    # Gesamtwelle
    points = []
    for i in range(elements + 1):
        x_norm = i / elements
        x = left + x_norm * length
        y = middle_y - y_scale * displacement_1d(x_norm, phase)
        points.append((x, y))

    draw_polyline(points, color="#1d4ed8", width=3, alpha=1.0)
    draw_points(points, radius=4, color="#1d4ed8", alpha=1.0)

    # Feste Enden hervorheben
    draw_points([points[0], points[-1]], radius=6, color="#c2410c", alpha=1.0)
    draw_wall_support(left - 8, middle_y, side="left")
    draw_wall_support(right + 8, middle_y, side="right")

    # Kleine Beschriftung
    ctx.save()
    ctx.fillStyle = "#475569"
    ctx.font = "18px system-ui"
    ctx.fillText("feste Enden: y = 0", left, middle_y + 90)
    ctx.fillText(f"{elements} Elemente, {elements + 1} Knoten", left, middle_y + 118)
    ctx.restore()


def grid_points_2d(single_mode=None, rest_position=False):
    """
    Berechnet alle Gitterpunkte für die 2D-Darstellung.

    Die Zahl im Slider beschreibt die inneren Massen pro Richtung.
    Bei 3 entsteht also ein 3 x 3 bewegliches Massengitter.
    Zusätzlich zeichnen wir außen einen festen Rand. Dadurch gibt es visuell
    insgesamt (3+2) x (3+2) Punkte, wobei nur die inneren Punkte schwingen.
    """
    width = canvas.width
    height = canvas.height

    inner = int_value("mode_count_2d_slider", 3)
    total = inner + 2

    # Das Gitter soll in die Canvas passen.
    grid_width = min(width * 0.68, height * 0.72)
    grid_height = grid_width
    left = (width - grid_width) / 2
    top = (height - grid_height) / 2

    # Skalenfaktor für die in-plane-Verschiebung.
    # Die Summe mehrerer Moden wird durch die Wurzel der aktiven Moden etwas
    # gedämpft, damit das Gitter nicht sofort zu stark verzerrt.
    visual_scale = float_value("displacement_scale_2d_slider", 1.0)
    active_count = max(1, count_active_2d_modes())
    displacement_scale = grid_width * 0.11 * visual_scale / sqrt(active_count)

    points = []
    for j in range(total):
        row = []
        v = j / (total - 1)
        for i in range(total):
            u = i / (total - 1)

            base_x = left + u * grid_width
            base_y = top + v * grid_height

            is_border = i == 0 or i == total - 1 or j == 0 or j == total - 1

            if rest_position or is_border:
                dx, dy = 0.0, 0.0
            else:
                dx, dy = displacement_2d(u, v, phase, single_mode=single_mode)

            x = base_x + dx * displacement_scale
            y = base_y + dy * displacement_scale
            row.append((x, y))
        points.append(row)

    return points


def draw_wire_grid(points, color="#1d4ed8", width=2, alpha=1.0):
    """Zeichnet ein Drahtgitter aus einer 2D-Punktliste."""
    ny = len(points)
    nx = len(points[0])

    ctx.save()
    ctx.globalAlpha = alpha
    ctx.strokeStyle = color
    ctx.lineWidth = width

    # Horizontale Gitterlinien
    for j in range(ny):
        ctx.beginPath()
        ctx.moveTo(points[j][0][0], points[j][0][1])
        for i in range(1, nx):
            ctx.lineTo(points[j][i][0], points[j][i][1])
        ctx.stroke()

    # Vertikale Gitterlinien
    for i in range(nx):
        ctx.beginPath()
        ctx.moveTo(points[0][i][0], points[0][i][1])
        for j in range(1, ny):
            ctx.lineTo(points[j][i][0], points[j][i][1])
        ctx.stroke()

    ctx.restore()


def count_active_2d_modes():
    """Zählt, wie viele aktuell sichtbare 2D-Moden eingeschaltet sind."""
    mode_count = int_value("mode_count_2d_slider", 3)
    count = 0
    for m in range(1, mode_count + 1):
        for n in range(1, mode_count + 1):
            if active_modes_2d[(m, n)]:
                count += 1
    return count


def active_2d_mode_text():
    """Erzeugt einen kurzen Text wie '(1,1), (2,1)' für die Anzeige."""
    mode_count = int_value("mode_count_2d_slider", 3)
    active = []
    for n in range(1, mode_count + 1):
        for m in range(1, mode_count + 1):
            if active_modes_2d[(m, n)]:
                active.append(f"({m},{n})")
    if not active:
        return "keine"
    return ", ".join(active)


def draw_2d():
    """Zeichnet das 2D-Gitter mit in-plane-Schwingung."""
    clear_canvas()

    mode_count = int_value("mode_count_2d_slider", 3)
    show_modes = is_checked("show_modes_checkbox", True)

    # Ruhelage des Gitters als sehr helle Orientierung.
    rest_points = grid_points_2d(rest_position=True)
    draw_wire_grid(rest_points, color="#cbd5e1", width=1, alpha=0.55)

    # Einzelmoden transparent im Hintergrund.
    # Nur eingeschaltete Moden werden gezeigt.
    if show_modes:
        for m in range(1, mode_count + 1):
            for n in range(1, mode_count + 1):
                if not active_modes_2d[(m, n)]:
                    continue
                mode_points = grid_points_2d(single_mode=(m, n))
                draw_wire_grid(mode_points, color="#64748b", width=1, alpha=0.14)

    # Gesamtgitter
    points = grid_points_2d(single_mode=None)
    draw_wire_grid(points, color="#1d4ed8", width=2.2, alpha=1.0)

    # Innere bewegliche Massen und feste Randpunkte getrennt markieren.
    total = mode_count + 2
    border = []
    inner_points = []
    for j in range(total):
        for i in range(total):
            if i == 0 or i == total - 1 or j == 0 or j == total - 1:
                border.append(points[j][i])
            else:
                inner_points.append(points[j][i])

    draw_points(inner_points, radius=4.2, color="#1d4ed8", alpha=1.0)
    draw_points(border, radius=4.2, color="#c2410c", alpha=1.0)

    # Beschriftung
    ctx.save()
    ctx.fillStyle = "#475569"
    ctx.font = "18px system-ui"
    ctx.fillText("feste Ränder: Randpunkte bleiben unbeweglich", 34, 42)
    ctx.fillText(f"{mode_count} × {mode_count} innere Massen, aktive Moden: {active_2d_mode_text()}", 34, 70)
    ctx.fillText("In-Plane-Schwingung: keine z-Achse", 34, 98)
    ctx.restore()


def draw():
    """Zeichnet den aktuellen Zustand des gewählten Modells."""
    model = el("model_select")
    if model is not None and model.value == "1d":
        draw_1d()
    else:
        draw_2d()


# ---------------------------------------------------------------------------
# Event-Handler
# ---------------------------------------------------------------------------


def on_input(event=None):
    """
    Allgemeiner Handler für Slider, Checkboxen und Auswahlfelder.

    Dieser Handler wird sehr häufig verwendet:
    - Sliderwerte speichern
    - Labels aktualisieren
    - Szene neu zeichnen
    """
    global phase

    read_current_1d_amplitudes()

    # Der Phasenslider speichert Gradwerte. Intern rechnen wir in Radiant.
    phase_degrees = float_value("phase_slider", 0.0)
    phase = phase_degrees / 360 * 2 * pi

    update_labels()
    draw()


def on_rebuild_1d(event=None):
    """Wird aufgerufen, wenn sich die Anzahl sichtbarer 1D-Moden ändert."""
    read_current_1d_amplitudes()
    build_1d_amplitude_controls()
    update_labels()
    draw()


def on_rebuild_2d(event=None):
    """Wird aufgerufen, wenn sich die 2D-Matrixgröße ändert."""
    build_2d_mode_matrix_controls()
    update_labels()
    draw()


def on_toggle_2d_mode(event=None):
    """Schaltet ein Kästchen der 2D-Modenmatrix ein oder aus."""
    target = event.currentTarget
    m = int(target.getAttribute("data-m"))
    n = int(target.getAttribute("data-n"))

    active_modes_2d[(m, n)] = not active_modes_2d[(m, n)]

    # Matrix neu zeichnen, damit die aktive Markierung sichtbar aktualisiert wird.
    build_2d_mode_matrix_controls()
    update_labels()
    draw()


def on_model_change(event=None):
    """Schaltet zwischen 1D-Saite und 2D-Gitter um."""
    read_current_1d_amplitudes()
    update_visible_controls()
    update_labels()
    draw()


def on_play_pause(event=None):
    """Startet oder pausiert die Animation."""
    global is_running, last_timestamp

    is_running = not is_running
    last_timestamp = None

    if is_running:
        set_text("play_button", "⏸ Pause")
        set_text("status_text", "Läuft")
    else:
        set_text("play_button", "▶ Play")
        set_text("status_text", "Pause")


def on_reset(event=None):
    """Setzt die Phase auf 0 zurück."""
    global phase, last_timestamp

    phase = 0.0
    last_timestamp = None
    phase_slider = el("phase_slider")
    if phase_slider is not None:
        phase_slider.value = 0
    update_labels()
    draw()


# ---------------------------------------------------------------------------
# Animationsschleife
# ---------------------------------------------------------------------------


def animate(timestamp):
    """
    Haupt-Animationsfunktion.

    requestAnimationFrame ruft diese Funktion ungefähr einmal pro Bildschirmframe auf.
    timestamp ist die aktuelle Browserzeit in Millisekunden.
    """
    global phase, last_timestamp

    if is_running:
        if last_timestamp is None:
            last_timestamp = timestamp

        dt = (timestamp - last_timestamp) / 1000
        last_timestamp = timestamp

        speed = float_value("speed_slider", 1.0)

        # Grundkreisfrequenz für die Animation.
        # Der Zahlenwert ist keine reale Einheit, sondern nur eine angenehme Animationsgeschwindigkeit.
        omega_base = 1.4
        phase += omega_base * speed * dt

        # Phasenslider synchronisieren.
        phase_degrees = (phase % (2 * pi)) / (2 * pi) * 360
        phase_slider = el("phase_slider")
        if phase_slider is not None:
            phase_slider.value = phase_degrees
        update_labels()
        draw()

    # Die Animationsschleife läuft dauerhaft weiter.
    # Gezeichnet wird aber nur dann fortlaufend, wenn is_running = True ist.
    window.requestAnimationFrame(animate_proxy)


# ---------------------------------------------------------------------------
# Initialisierung
# ---------------------------------------------------------------------------


# Proxies für Browser-Callbacks erzeugen.
on_input_proxy = create_proxy(on_input)
on_rebuild_1d_proxy = create_proxy(on_rebuild_1d)
on_rebuild_2d_proxy = create_proxy(on_rebuild_2d)
on_toggle_2d_mode_proxy = create_proxy(on_toggle_2d_mode)
on_model_change_proxy = create_proxy(on_model_change)
on_play_pause_proxy = create_proxy(on_play_pause)
on_reset_proxy = create_proxy(on_reset)
animate_proxy = create_proxy(animate)

_proxies.extend([
    on_input_proxy,
    on_rebuild_1d_proxy,
    on_rebuild_2d_proxy,
    on_toggle_2d_mode_proxy,
    on_model_change_proxy,
    on_play_pause_proxy,
    on_reset_proxy,
    animate_proxy,
])

# Statische Bedienelemente mit Event-Handlern verbinden.
el("model_select").addEventListener("change", on_model_change_proxy)
el("play_button").addEventListener("click", on_play_pause_proxy)
el("reset_button").addEventListener("click", on_reset_proxy)

# Normale Slider, Checkboxen und Auswahlfelder.
for element_id in [
    "speed_slider",
    "phase_slider",
    "elements_1d_slider",
    "displacement_scale_2d_slider",
    "physical_frequency_checkbox",
    "show_modes_checkbox",
]:
    element = el(element_id)
    if element is not None:
        element.addEventListener("input", on_input_proxy)

# Auswahlfeld für die globale 2D-Schwingungsrichtung.
direction_selector = el("direction_2d_select")
if direction_selector is not None:
    direction_selector.addEventListener("change", on_input_proxy)

# Diese Slider verändern dynamisch erzeugte Bedienelemente.
el("active_modes_1d_slider").addEventListener("input", on_rebuild_1d_proxy)
el("mode_count_2d_slider").addEventListener("input", on_rebuild_2d_proxy)

# Oberfläche aufbauen und erste Szene zeichnen.
build_1d_amplitude_controls()
build_2d_mode_matrix_controls()
update_visible_controls()
update_labels()
draw()

# Animationsschleife starten.
window.requestAnimationFrame(animate_proxy)
