"""
Zeigerformalismus – Grundlagen
==============================

Dieses PyScript-Applet zeigt den Zusammenhang zwischen geometrischer
Vektoraddition und dem Zeigerformalismus.

Didaktische Trennung:
    Vektor: geometrischer Pfeil mit Richtung und Länge.
    Zeiger: Vektor in der komplexen Ebene, beschreibt Amplitude und Phase.
    Wahrscheinlichkeitsamplitude: QED-Deutung eines Zeigers.

Bedienidee:
    - Im freien Vektormodus werden Pfeile direkt im Canvas gezeichnet.
    - Im QED-/Zeigermodus starten neue Zeiger im Ursprung der komplexen Ebene.
    - Ein Klick auf einen bestehenden Pfeil wählt ihn aus.
    - Start- und Endpunkt können im Vektormodus verschoben werden.
    - Im Zeigermodus bleibt der Startpunkt am Ursprung; der Endpunkt bestimmt
      Amplitude und Phase.
"""

import math
from js import document, window
from pyodide.ffi import create_proxy

# -----------------------------------------------------------------------------
# DOM-Elemente
# -----------------------------------------------------------------------------

canvas = document.getElementById("phasor-canvas")
ctx = canvas.getContext("2d")

mode_select = document.getElementById("mode-select")
preset_select = document.getElementById("preset-select")

result_toggle = document.getElementById("result-toggle")
phase_toggle = document.getElementById("phase-toggle")
square_toggle = document.getElementById("square-toggle")
individual_toggle = document.getElementById("individual-toggle")
axis_label_toggle = document.getElementById("axis-label-toggle")
formula_toggle = document.getElementById("formula-toggle")

undo_button = document.getElementById("undo-button")
delete_button = document.getElementById("delete-button")
reset_button = document.getElementById("reset-button")

qed_controls = document.getElementById("qed-controls")
wavelength_slider = document.getElementById("wavelength-slider")
path_slider = document.getElementById("path-slider")
wavelength_readout = document.getElementById("wavelength-readout")
path_readout = document.getElementById("path-readout")
color_preview = document.getElementById("color-preview")
color_name = document.getElementById("color-name")

formula_panel = document.getElementById("formula-panel")
formula_lambda = document.getElementById("formula-lambda")
formula_path = document.getElementById("formula-path")
formula_phase = document.getElementById("formula-phase")
path_phase_formula = document.getElementById("path-phase-formula")
sum_formula = document.getElementById("sum-formula")
probability_formula = document.getElementById("probability-formula")

count_readout = document.getElementById("count-readout")
result_readout = document.getElementById("result-readout")
phase_readout = document.getElementById("phase-readout")
square_readout = document.getElementById("square-readout")
mode_badge = document.getElementById("mode-badge")
interaction_hint = document.getElementById("interaction-hint")

# -----------------------------------------------------------------------------
# Konstanten und Zustand
# -----------------------------------------------------------------------------

WIDTH = canvas.width
HEIGHT = canvas.height
CX = WIDTH / 2
CY = HEIGHT / 2

UNIT = 60.0               # 60 Pixel entsprechen einer Anzeigeeinheit
MIN_LENGTH = 8.0          # sehr kurze Mauszüge werden ignoriert
SNAP_DISTANCE = 22.0      # Abstand, ab dem ein Startpunkt einrastet
HANDLE_RADIUS = 8.0
HIT_DISTANCE = 9.0

vectors = []              # Liste aus Dicts: {sx, sy, ex, ey, color}
selected_index = None
preview_vector = None

is_dragging = False
drag_mode = None          # "new", "start", "end", "move"
drag_start_pos = None
drag_original = None

_proxies = []             # Event-Proxies müssen gespeichert bleiben

# -----------------------------------------------------------------------------
# Kleine Hilfsfunktionen
# -----------------------------------------------------------------------------

def fmt(value, digits=2):
    """Deutsche Dezimalschreibweise für kurze Anzeigen."""
    return f"{value:.{digits}f}".replace(".", ",")


def clamp(value, lower, upper):
    return max(lower, min(upper, value))


def distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def canvas_pos(event):
    """Mausposition in Canvas-Pixelkoordinaten."""
    rect = canvas.getBoundingClientRect()
    scale_x = WIDTH / rect.width
    scale_y = HEIGHT / rect.height
    return (
        (event.clientX - rect.left) * scale_x,
        (event.clientY - rect.top) * scale_y,
    )


def origin():
    return (CX, CY)


def vector_components(v):
    """Komponenten in Pixelkoordinaten."""
    return (v["ex"] - v["sx"], v["ey"] - v["sy"])


def vector_complex(v):
    """
    Umrechnung in komplexe Anzeigeeinheiten.
    Die Canvas-y-Achse zeigt nach unten; die mathematische Imaginärachse nach oben.
    """
    dx, dy = vector_components(v)
    return (dx / UNIT, -dy / UNIT)


def resultant_complex():
    re = 0.0
    im = 0.0
    for v in vectors:
        z_re, z_im = vector_complex(v)
        re += z_re
        im += z_im
    return re, im


def resultant_pixels():
    dx = 0.0
    dy = 0.0
    for v in vectors:
        vx, vy = vector_components(v)
        dx += vx
        dy += vy
    return dx, dy


def vector_length(v):
    dx, dy = vector_components(v)
    return math.hypot(dx, dy)


def phase_deg(re, im):
    if abs(re) < 1e-12 and abs(im) < 1e-12:
        return None
    return math.degrees(math.atan2(im, re))


def complex_string(re, im):
    """Kurze Anzeige einer komplexen Zahl mit sauberem Vorzeichen."""
    sign = "+" if im >= 0 else "−"
    return f"{fmt(re)} {sign} {fmt(abs(im))} i"


def wavelength_value():
    return float(wavelength_slider.value)


def path_value():
    return float(path_slider.value)


def current_mode():
    return mode_select.value


def current_color():
    rgb, _ = wavelength_to_rgb_and_name(wavelength_value())
    return rgb

# -----------------------------------------------------------------------------
# Farbe sichtbarer Wellenlängen
# -----------------------------------------------------------------------------

def mix(a, b, t):
    return round(a + (b - a) * t)


def interpolate_rgb(c1, c2, t):
    t = clamp(t, 0.0, 1.0)
    return (
        mix(c1[0], c2[0], t),
        mix(c1[1], c2[1], t),
        mix(c1[2], c2[2], t),
    )


def rgb_string(rgb):
    return f"rgb({rgb[0]}, {rgb[1]}, {rgb[2]})"


def wavelength_to_rgb_and_name(wavelength_nm):
    """
    Qualitative sRGB-Näherung für sichtbare Wellenlängen.
    Ein Bildschirm kann Spektralfarben nicht exakt darstellen; die Bereiche folgen
    den im Unterricht üblichen Farbnamen.
    """
    w = clamp(wavelength_nm, 380, 740)

    violet = (126, 72, 255)
    blue = (35, 88, 255)
    cyan = (0, 188, 220)
    green = (40, 190, 86)
    yellow = (246, 218, 62)
    orange = (240, 132, 37)
    red = (225, 46, 45)
    deep_red = (150, 25, 35)

    if w < 440:
        t = (w - 380) / (440 - 380)
        return rgb_string(interpolate_rgb(violet, blue, t)), "violett"
    if w < 485:
        t = (w - 440) / (485 - 440)
        return rgb_string(interpolate_rgb(blue, cyan, t)), "blau"
    if w < 510:
        t = (w - 485) / (510 - 485)
        return rgb_string(interpolate_rgb(cyan, green, t)), "cyan"
    if w < 565:
        t = (w - 510) / (565 - 510)
        return rgb_string(interpolate_rgb(green, yellow, t)), "grün"
    if w < 590:
        t = (w - 565) / (590 - 565)
        return rgb_string(interpolate_rgb(yellow, orange, t)), "gelb"
    if w < 625:
        t = (w - 590) / (625 - 590)
        return rgb_string(interpolate_rgb(orange, red, t)), "orange"

    t = (w - 625) / (740 - 625)
    return rgb_string(interpolate_rgb(red, deep_red, t)), "rot"

# -----------------------------------------------------------------------------
# Zeichnen auf dem Canvas
# -----------------------------------------------------------------------------

def draw_line(x1, y1, x2, y2, color="#1f2937", width=2.5, dash=None, alpha=1.0):
    ctx.save()
    ctx.globalAlpha = alpha
    ctx.strokeStyle = color
    ctx.lineWidth = width
    ctx.lineCap = "round"
    if dash:
        ctx.setLineDash(dash)
    else:
        ctx.setLineDash([])
    ctx.beginPath()
    ctx.moveTo(x1, y1)
    ctx.lineTo(x2, y2)
    ctx.stroke()
    ctx.restore()


def draw_arrow(x1, y1, x2, y2, color="#4257ff", width=3.0, alpha=1.0, label=None, dashed=False):
    dx = x2 - x1
    dy = y2 - y1
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return

    angle = math.atan2(dy, dx)
    head_len = min(16, max(9, length * 0.18))
    head_ang = math.radians(26)

    ctx.save()
    ctx.globalAlpha = alpha
    ctx.strokeStyle = color
    ctx.fillStyle = color
    ctx.lineWidth = width
    ctx.lineCap = "round"
    ctx.lineJoin = "round"
    if dashed:
        ctx.setLineDash([8, 7])

    ctx.beginPath()
    ctx.moveTo(x1, y1)
    ctx.lineTo(x2, y2)
    ctx.stroke()

    ax1 = x2 - head_len * math.cos(angle - head_ang)
    ay1 = y2 - head_len * math.sin(angle - head_ang)
    ax2 = x2 - head_len * math.cos(angle + head_ang)
    ay2 = y2 - head_len * math.sin(angle + head_ang)

    ctx.beginPath()
    ctx.moveTo(x2, y2)
    ctx.lineTo(ax1, ay1)
    ctx.lineTo(ax2, ay2)
    ctx.closePath()
    ctx.fill()

    if label:
        ctx.font = "700 14px Inter, system-ui, sans-serif"
        ctx.fillText(label, x2 + 9, y2 - 9)

    ctx.restore()


def draw_handle(x, y, color="#ffffff", border="#4257ff", radius=HANDLE_RADIUS):
    ctx.save()
    ctx.fillStyle = color
    ctx.strokeStyle = border
    ctx.lineWidth = 2.5
    ctx.beginPath()
    ctx.arc(x, y, radius, 0, 2 * math.pi)
    ctx.fill()
    ctx.stroke()
    ctx.restore()


def draw_grid_and_axes():
    ctx.clearRect(0, 0, WIDTH, HEIGHT)

    # feines Raster
    ctx.save()
    ctx.strokeStyle = "#edf2f8"
    ctx.lineWidth = 1
    step = UNIT
    x = CX % step
    while x <= WIDTH:
        ctx.beginPath()
        ctx.moveTo(x, 0)
        ctx.lineTo(x, HEIGHT)
        ctx.stroke()
        x += step

    y = CY % step
    while y <= HEIGHT:
        ctx.beginPath()
        ctx.moveTo(0, y)
        ctx.lineTo(WIDTH, y)
        ctx.stroke()
        y += step
    ctx.restore()

    # Hauptachsen ohne abschreckende Beschriftung
    draw_line(0, CY, WIDTH, CY, color="#d2dae8", width=1.7)
    draw_line(CX, 0, CX, HEIGHT, color="#d2dae8", width=1.7)

    # Ursprung
    ctx.save()
    ctx.fillStyle = "#9aa8bd"
    ctx.beginPath()
    ctx.arc(CX, CY, 3.5, 0, 2 * math.pi)
    ctx.fill()
    ctx.restore()

    if axis_label_toggle.checked:
        ctx.save()
        ctx.fillStyle = "#657286"
        ctx.font = "700 14px Inter, system-ui, sans-serif"
        ctx.fillText("Realteil", WIDTH - 82, CY - 12)
        ctx.fillText("Imaginärteil", CX + 12, 22)
        ctx.fillText("0", CX + 8, CY + 18)
        ctx.restore()


def draw_phase_arc_for_result(start_x, start_y, end_x, end_y):
    if not phase_toggle.checked:
        return

    dx = end_x - start_x
    dy = end_y - start_y
    if math.hypot(dx, dy) < 12:
        return

    # mathematischer Winkel: y-Achse nach oben
    angle_math = math.atan2(-dy, dx)
    angle_canvas = -angle_math
    radius = 52

    ctx.save()
    ctx.strokeStyle = "#f59e0b"
    ctx.fillStyle = "#b45309"
    ctx.lineWidth = 2
    ctx.beginPath()
    ctx.arc(start_x, start_y, radius, 0, angle_canvas, angle_canvas < 0)
    ctx.stroke()
    ctx.font = "700 13px Inter, system-ui, sans-serif"
    ctx.fillText("φ", start_x + radius + 8, start_y - 8)
    ctx.restore()


def draw_vector(v, index, alpha=1.0):
    label = None
    if individual_toggle.checked:
        z_re, z_im = vector_complex(v)
        mag = math.hypot(z_re, z_im)
        symbol = "z" if current_mode() == "qed" else "v"
        label = f"{symbol}{index + 1}: {fmt(mag)}"

    width = 3.2 if index == selected_index else 2.6
    draw_arrow(v["sx"], v["sy"], v["ex"], v["ey"], color=v["color"], width=width, alpha=alpha, label=label)

    if index == selected_index:
        draw_handle(v["sx"], v["sy"], border="#0f172a")
        draw_handle(v["ex"], v["ey"], border="#0f172a")


def draw_qed_addition_chain():
    """Im Zeigermodus wird zusätzlich eine Kopf-an-Schwanz-Kopie gezeigt."""
    if current_mode() != "qed" or len(vectors) < 2:
        return

    x, y = CX, CY
    for i, v in enumerate(vectors):
        dx, dy = vector_components(v)
        nx = x + dx
        ny = y + dy
        draw_arrow(x, y, nx, ny, color=v["color"], width=2.0, alpha=0.32, dashed=True)
        x, y = nx, ny

def draw_square_on_resultant(sx, sy, ex, ey):
    """
    Zeichnet ein Quadrat über der Resultierenden.
    Die Resultierende bildet eine Seite des Quadrats.
    Die Fläche dient als geometrische Merkhilfe für |R|² bzw. |z_ges|².
    """
    dx = ex - sx
    dy = ey - sy
    length = math.hypot(dx, dy)

    if length < 10:
        return

    # Zwei mögliche Quadrate: links oder rechts der Resultierenden.
    normal_a = (-dy, dx)
    normal_b = (dy, -dx)

    def overflow_score(nx, ny):
        points = [
            (sx, sy),
            (ex, ey),
            (ex + nx, ey + ny),
            (sx + nx, sy + ny),
        ]

        score = 0
        for px, py in points:
            if px < 0:
                score += abs(px)
            if px > WIDTH:
                score += px - WIDTH
            if py < 0:
                score += abs(py)
            if py > HEIGHT:
                score += py - HEIGHT
        return score

    if overflow_score(*normal_b) < overflow_score(*normal_a):
        nx, ny = normal_b
    else:
        nx, ny = normal_a

    label = "|zges|²" if current_mode() == "qed" else "|R|²"

    ctx.save()
    ctx.fillStyle = "rgba(17, 24, 39, 0.075)"
    ctx.strokeStyle = "rgba(17, 24, 39, 0.32)"
    ctx.lineWidth = 1.8
    ctx.setLineDash([7, 6])

    ctx.beginPath()
    ctx.moveTo(sx, sy)
    ctx.lineTo(ex, ey)
    ctx.lineTo(ex + nx, ey + ny)
    ctx.lineTo(sx + nx, sy + ny)
    ctx.closePath()
    ctx.fill()
    ctx.stroke()

    # kleines Rechtwinkelsymbol am Startpunkt
    ux = dx / length
    uy = dy / length
    vx = nx / length
    vy = ny / length
    marker = min(22, length * 0.18)

    ctx.setLineDash([])
    ctx.strokeStyle = "rgba(17, 24, 39, 0.55)"
    ctx.beginPath()
    ctx.moveTo(sx + ux * marker, sy + uy * marker)
    ctx.lineTo(sx + ux * marker + vx * marker, sy + uy * marker + vy * marker)
    ctx.lineTo(sx + vx * marker, sy + vy * marker)
    ctx.stroke()

    ctx.fillStyle = "#111827"
    ctx.font = "700 14px Inter, system-ui, sans-serif"
    ctx.fillText(label, sx + nx * 0.5 + dx * 0.5 - 18, sy + ny * 0.5 + dy * 0.5)

    ctx.restore()


def draw_resultant():
    if not result_toggle.checked or not vectors:
        return

    dx, dy = resultant_pixels()

    if current_mode() == "qed":
        sx, sy = CX, CY
        label = "z"
    else:
        sx, sy = vectors[0]["sx"], vectors[0]["sy"]
        label = "R"

    ex = sx + dx
    ey = sy + dy

    # Das Betragsquadrat wird als Fläche zur Resultierenden gezeichnet.
    # Die Resultierende selbst bleibt als eine Seite des Quadrats sichtbar.
    if square_toggle.checked:
        draw_square_on_resultant(sx, sy, ex, ey)

    draw_arrow(sx, sy, ex, ey, color="#111827", width=4.0, alpha=0.95, label=label)
    draw_phase_arc_for_result(sx, sy, ex, ey)


def draw_path_phase_helper():
    """Kleine Zusatzanzeige im Zeigermodus: Phase aus Wegunterschied und Wellenlänge."""
    if current_mode() != "qed":
        return

    lam = wavelength_value()
    ds = path_value()
    phi = 2 * math.pi * ds / lam
    phi_mod = phi % (2 * math.pi)
    length = 78
    x1 = 82
    y1 = 82
    x2 = x1 + length * math.cos(phi_mod)
    y2 = y1 - length * math.sin(phi_mod)
    color = current_color()

    ctx.save()
    ctx.fillStyle = "rgba(255, 255, 255, 0.86)"
    ctx.strokeStyle = "#d8e0ec"
    ctx.lineWidth = 1
    ctx.beginPath()
    ctx.roundRect(22, 24, 190, 126, 16)
    ctx.fill()
    ctx.stroke()
    ctx.fillStyle = "#657286"
    ctx.font = "700 12px Inter, system-ui, sans-serif"
    ctx.fillText("Phase aus Δs und λ", 40, 50)
    ctx.restore()

    draw_line(x1 - 46, y1, x1 + 96, y1, color="#e2e8f0", width=1.2)
    draw_line(x1, y1 + 46, x1, y1 - 46, color="#e2e8f0", width=1.2)
    draw_arrow(x1, y1, x2, y2, color=color, width=3.0, label=None)

    ctx.save()
    ctx.fillStyle = "#142033"
    ctx.font = "700 12px Inter, system-ui, sans-serif"
    ctx.fillText(f"φ mod 2π = {fmt(phi_mod)} rad", 40, 132)
    ctx.restore()


def draw_preview():
    if preview_vector is None:
        return
    draw_arrow(
        preview_vector["sx"], preview_vector["sy"],
        preview_vector["ex"], preview_vector["ey"],
        color=preview_vector["color"],
        width=2.2,
        alpha=0.55,
        dashed=True,
    )


def draw_all():
    draw_grid_and_axes()
    draw_path_phase_helper()

    if current_mode() == "qed":
        # Im Zeigermodus hilft die gestrichelte Kopie beim Verständnis der Addition.
        draw_qed_addition_chain()

    for i, v in enumerate(vectors):
        draw_vector(v, i)

    draw_preview()
    draw_resultant()

# -----------------------------------------------------------------------------
# Trefferlogik und Interaktion
# -----------------------------------------------------------------------------

def point_to_segment_distance(px, py, x1, y1, x2, y2):
    dx = x2 - x1
    dy = y2 - y1
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return math.hypot(px - x1, py - y1)
    t = ((px - x1) * dx + (py - y1) * dy) / length_sq
    t = clamp(t, 0.0, 1.0)
    nearest_x = x1 + t * dx
    nearest_y = y1 + t * dy
    return math.hypot(px - nearest_x, py - nearest_y)


def hit_test(pos):
    """Gibt (index, trefferart) zurück: start, end, body oder None."""
    px, py = pos

    # Handles haben Vorrang, beginnend beim zuletzt gezeichneten Pfeil.
    for i in range(len(vectors) - 1, -1, -1):
        v = vectors[i]
        if distance(pos, (v["ex"], v["ey"])) <= HANDLE_RADIUS + 4:
            return i, "end"
        if current_mode() != "qed" and distance(pos, (v["sx"], v["sy"])) <= HANDLE_RADIUS + 4:
            return i, "start"

    for i in range(len(vectors) - 1, -1, -1):
        v = vectors[i]
        d = point_to_segment_distance(px, py, v["sx"], v["sy"], v["ex"], v["ey"])
        if d <= HIT_DISTANCE:
            return i, "body"

    return None, None


def nearest_snap_point(pos, exclude_index=None):
    """
    Sucht einen geeigneten Fangpunkt.
    Gefangen wird am Ursprung sowie an Start- und Endpunkten anderer Vektoren.
    Der gerade bearbeitete Vektor wird ausgeschlossen, damit er nicht auf sich selbst einrastet.
    """
    candidates = [origin()]

    # Zuletzt gezeichnete Vektoren werden zuerst geprüft.
    # Das fühlt sich beim Weiterzeichnen der Pfeilkette natürlicher an.
    for i in range(len(vectors) - 1, -1, -1):
        if i == exclude_index:
            continue

        v = vectors[i]
        candidates.append((v["ex"], v["ey"]))
        candidates.append((v["sx"], v["sy"]))

    best = None
    best_dist = SNAP_DISTANCE

    for candidate in candidates:
        d = distance(pos, candidate)
        if d <= best_dist:
            best = candidate
            best_dist = d

    return best


def snap_point(pos, exclude_index=None):
    """Gibt den eingerasteten Punkt zurück oder unverändert die Mausposition."""
    target = nearest_snap_point(pos, exclude_index=exclude_index)
    if target is not None:
        return target
    return pos


def snap_whole_vector(sx, sy, ex, ey, exclude_index=None):
    """
    Verschiebt einen ganzen Vektor so, dass Start- oder Endpunkt einrasten kann.
    Priorität: Startpunkt vor Endpunkt.
    """
    start_target = nearest_snap_point((sx, sy), exclude_index=exclude_index)
    if start_target is not None:
        dx = start_target[0] - sx
        dy = start_target[1] - sy
        return sx + dx, sy + dy, ex + dx, ey + dy

    end_target = nearest_snap_point((ex, ey), exclude_index=exclude_index)
    if end_target is not None:
        dx = end_target[0] - ex
        dy = end_target[1] - ey
        return sx + dx, sy + dy, ex + dx, ey + dy

    return sx, sy, ex, ey


def set_cursor(kind):
    canvas.style.cursor = kind


def on_mouse_down(event):
    global selected_index, is_dragging, drag_mode, drag_start_pos, drag_original, preview_vector

    event.preventDefault()
    pos = canvas_pos(event)
    index, kind = hit_test(pos)

    if index is not None:
        selected_index = index
        is_dragging = True
        drag_start_pos = pos
        drag_original = vectors[index].copy()

        if kind == "end":
            drag_mode = "end"
        elif kind == "start":
            drag_mode = "start"
        else:
            drag_mode = "move" if current_mode() != "qed" else "end"

        preview_vector = None
        update_readouts()
        draw_all()
        return

    selected_index = None
    is_dragging = True
    drag_mode = "new"
    drag_start_pos = origin() if current_mode() == "qed" else snap_point(pos)
    drag_original = None

    preview_vector = {
        "sx": drag_start_pos[0],
        "sy": drag_start_pos[1],
        "ex": pos[0],
        "ey": pos[1],
        "color": current_color() if current_mode() == "qed" else "#4257ff",
    }
    draw_all()


def on_mouse_move(event):
    global preview_vector

    pos = canvas_pos(event)

    if not is_dragging:
        index, kind = hit_test(pos)
        if kind in ("start", "end"):
            set_cursor("grab")
        elif kind == "body":
            set_cursor("pointer")
        else:
            set_cursor("crosshair")
        return

    if drag_mode == "new" and preview_vector:
        end_pos = snap_point(pos)
        preview_vector["ex"] = end_pos[0]
        preview_vector["ey"] = end_pos[1]
        draw_all()
        return

    if selected_index is None or drag_original is None:
        return

    v = vectors[selected_index]

    if drag_mode == "end":
        end_pos = snap_point(pos, exclude_index=selected_index)
        v["ex"] = end_pos[0]
        v["ey"] = end_pos[1]
    
        if current_mode() == "qed":
            v["sx"], v["sy"] = origin()
    
    elif drag_mode == "start" and current_mode() != "qed":
        start_pos = snap_point(pos, exclude_index=selected_index)
        v["sx"] = start_pos[0]
        v["sy"] = start_pos[1]
    
    elif drag_mode == "move" and current_mode() != "qed":
        dx = pos[0] - drag_start_pos[0]
        dy = pos[1] - drag_start_pos[1]
    
        sx = drag_original["sx"] + dx
        sy = drag_original["sy"] + dy
        ex = drag_original["ex"] + dx
        ey = drag_original["ey"] + dy
    
        sx, sy, ex, ey = snap_whole_vector(
            sx, sy, ex, ey,
            exclude_index=selected_index,
        )
    
        v["sx"] = sx
        v["sy"] = sy
        v["ex"] = ex
        v["ey"] = ey

    update_readouts()
    draw_all()


def on_mouse_up(event):
    global is_dragging, drag_mode, drag_start_pos, drag_original, preview_vector, selected_index

    if not is_dragging:
        return

    if drag_mode == "new" and preview_vector:
        length = math.hypot(preview_vector["ex"] - preview_vector["sx"], preview_vector["ey"] - preview_vector["sy"])
        if length >= MIN_LENGTH:
            vectors.append(preview_vector.copy())
            selected_index = len(vectors) - 1

    is_dragging = False
    drag_mode = None
    drag_start_pos = None
    drag_original = None
    preview_vector = None

    update_readouts()
    draw_all()


def on_mouse_leave(event):
    on_mouse_up(event)

# -----------------------------------------------------------------------------
# Buttons, Presets und Anzeigen
# -----------------------------------------------------------------------------

def make_vector_from_polar(start_x, start_y, length, angle_deg, color="#4257ff"):
    angle = math.radians(angle_deg)
    return {
        "sx": start_x,
        "sy": start_y,
        "ex": start_x + length * math.cos(angle),
        "ey": start_y - length * math.sin(angle),
        "color": color,
    }


def add_polar_sequence(lengths, angles):
    """Erzeugt Presets passend zum aktuellen Modus."""
    vectors.clear()
    selected_index_reset()

    if current_mode() == "qed":
        color = current_color()
        for length, angle in zip(lengths, angles):
            vectors.append(make_vector_from_polar(CX, CY, length, angle, color=color))
    else:
        x, y = CX - 120, CY + 50
        for length, angle in zip(lengths, angles):
            v = make_vector_from_polar(x, y, length, angle, color="#4257ff")
            vectors.append(v)
            x, y = v["ex"], v["ey"]


def selected_index_reset():
    global selected_index
    selected_index = None


def apply_preset(name):
    global selected_index

    if name == "free":
        return

    if name == "constructive":
        add_polar_sequence([135, 135], [0, 0])
    elif name == "destructive":
        add_polar_sequence([135, 135], [0, 180])
    elif name == "right_angle":
        add_polar_sequence([135, 135], [0, 90])
    elif name == "six_steps":
        add_polar_sequence([82] * 6, [0, 18, 36, 54, 72, 90])
    elif name == "circle_cancel":
        count = 12
        add_polar_sequence([75] * count, [i * 360 / count for i in range(count)])
    elif name == "near_phase":
        count = 12
        add_polar_sequence([35] * count, [-24 + i * 48 / (count - 1) for i in range(count)])

    preset_select.value = name
    update_readouts()
    draw_all()


def on_preset_change(event):
    apply_preset(preset_select.value)


def undo_last(event=None):
    global selected_index
    if vectors:
        vectors.pop()
    selected_index = None
    preset_select.value = "free"
    update_readouts()
    draw_all()


def delete_selected(event=None):
    global selected_index
    if selected_index is not None and 0 <= selected_index < len(vectors):
        vectors.pop(selected_index)
        selected_index = None
        preset_select.value = "free"
    update_readouts()
    draw_all()


def reset_all(event=None):
    global selected_index, preview_vector
    vectors.clear()
    selected_index = None
    preview_vector = None
    preset_select.value = "free"
    update_readouts()
    draw_all()


def on_key_down(event):
    key = event.key
    if key in ("Backspace", "Delete"):
        delete_selected(event)
    elif key.lower() == "z" and (event.ctrlKey or event.metaKey):
        undo_last(event)


def on_mode_change(event):
    reset_all()
    update_mode_ui()


def update_mode_ui():
    mode = current_mode()

    if mode == "qed":
        mode_badge.textContent = "Zeigermodus"
        interaction_hint.textContent = (
            "Zeiger vom Ursprung aus zeichnen. "
            "Länge und Richtung bestimmen Amplitude und Phase."
        )
        qed_controls.classList.remove("hidden")
    else:
        mode_badge.textContent = "Vektormodus"
        interaction_hint.textContent = (
            "Zum Zeichnen klicken und ziehen. "
            "Pfeile können aneinander einrasten."
        )
        qed_controls.classList.add("hidden")

    update_color_ui()
    update_readouts()
    draw_all()


def update_formula_visibility(event=None):
    if formula_toggle.checked:
        formula_panel.classList.remove("hidden")
    else:
        formula_panel.classList.add("hidden")
    update_readouts()
    draw_all()


def update_color_ui(event=None):
    rgb, name = wavelength_to_rgb_and_name(wavelength_value())
    wavelength_readout.textContent = f"{int(wavelength_value())} nm"
    path_readout.textContent = f"{int(path_value())} nm"
    color_preview.style.background = rgb
    color_name.textContent = name

    # Im QED-Zeigermodus steht die Farbe für die aktuell gewählte Wellenlänge.
    # Deshalb werden bereits gezeichnete Zeiger beim Verschieben des Reglers mitgefärbt.
    if current_mode() == "qed":
        for v in vectors:
            v["color"] = rgb

    update_readouts()
    draw_all()


def update_readouts():
    re, im = resultant_complex()
    mag = math.hypot(re, im)
    mag_sq = mag * mag
    phi = phase_deg(re, im)

    count_readout.textContent = str(len(vectors))

    is_phasor = current_mode() == "qed"

    if is_phasor:
        result_readout.textContent = f"|zges| = {fmt(mag)}"
    else:
        result_readout.textContent = f"|R| = {fmt(mag)}"

    if phase_toggle.checked and phi is not None:
        phase_readout.textContent = f"φ = {fmt(phi, 1)}°"
    elif phase_toggle.checked:
        phase_readout.textContent = "φ = –"
    else:
        phase_readout.textContent = "–"

    if square_toggle.checked:
        if is_phasor:
            square_readout.textContent = f"|zges|² = {fmt(mag_sq)}"
        else:
            square_readout.textContent = f"|R|² = {fmt(mag_sq)}"
    else:
        square_readout.textContent = "–"

    if is_phasor:
        sum_formula.innerHTML = (
            f"z<sub>ges</sub> = Σ z<sub>n</sub> = {complex_string(re, im)}"
        )
        probability_formula.innerHTML = (
            f"|z<sub>ges</sub>|² = {fmt(mag_sq)}"
        )
    else:
        sum_formula.innerHTML = (
            f"R = Σ v<sub>n</sub> = ({fmt(re)}; {fmt(im)})"
        )
        probability_formula.innerHTML = f"|R|² = {fmt(mag_sq)}"

    lam = wavelength_value()
    ds = path_value()
    phi_rad = 2 * math.pi * ds / lam
    phi_mod = phi_rad % (2 * math.pi)

    formula_lambda.textContent = f"{int(lam)} nm"
    formula_path.textContent = f"{int(ds)} nm"
    formula_phase.textContent = f"{fmt(phi_mod)} rad"
    path_phase_formula.textContent = (
        f"φ = 2π · Δs / λ = 2π · {int(ds)} nm / {int(lam)} nm = {fmt(phi_rad)} rad"
    )

# -----------------------------------------------------------------------------
# Event-Bindings
# -----------------------------------------------------------------------------

def bind(element, event_name, handler):
    proxy = create_proxy(handler)
    element.addEventListener(event_name, proxy)
    _proxies.append(proxy)


bind(canvas, "mousedown", on_mouse_down)
bind(canvas, "mousemove", on_mouse_move)
bind(canvas, "mouseup", on_mouse_up)
bind(canvas, "mouseleave", on_mouse_leave)

bind(mode_select, "change", on_mode_change)
bind(preset_select, "change", on_preset_change)

bind(undo_button, "click", undo_last)
bind(delete_button, "click", delete_selected)
bind(reset_button, "click", reset_all)

for checkbox in [
    result_toggle,
    phase_toggle,
    square_toggle,
    individual_toggle,
    axis_label_toggle,
]:
    bind(checkbox, "change", lambda event: (update_readouts(), draw_all()))

bind(formula_toggle, "change", update_formula_visibility)
bind(wavelength_slider, "input", update_color_ui)
bind(path_slider, "input", update_color_ui)
bind(document, "keydown", on_key_down)

# Erster Aufbau
update_mode_ui()
update_formula_visibility()
