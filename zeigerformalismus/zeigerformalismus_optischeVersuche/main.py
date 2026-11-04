"""
Versuche zum Zeigerformalismus
==============================

Das Applet verbindet drei optische Versuchssituationen mit demselben
Rechenweg:

    optische Weglänge -> Phase -> komplexer Zeiger -> Summe -> Betragsquadrat

Die Datei ist bewusst in gemeinsame Zeichenwerkzeuge und drei voneinander
getrennte Versuchsmodule gegliedert. Dadurch können physikalische Modelle oder
Darstellungen später unabhängig erweitert werden.

Modellgrenzen:
    * Dünne Glasschicht: Zwei-Beitrags-Modell bei senkrechtem Einfall.
    * Spiegel: gleich gewichtete Beiträge diskreter Spiegelbereiche.
    * Beugung: ausschließlich Fraunhofer-Näherung (Fernfeld).

Die gezeichneten Linien sind alternative Beiträge zur Gesamtamplitude. Sie
werden nicht als gemessene Bahnen einzelner Photonen interpretiert.
"""

import math
from js import document
from pyodide.ffi import create_proxy


# =============================================================================
# DOM, Canvas und globaler Zustand
# =============================================================================

canvas = document.getElementById("experiment-canvas")
ctx = canvas.getContext("2d")

WIDTH = canvas.width
HEIGHT = canvas.height

# Die drei festen Zeichenbereiche halten das Layout bei allen Versuchen gleich.
GEOMETRY = (28, 26, 680, 338)
PHASOR = (734, 26, 438, 338)
GRAPH = (28, 390, 1144, 300)

state = {
    "experiment": "film",
    "hover_segment": None,
    "drag_target": None,
    # Quelle und Detektor des Spiegelversuchs in Modellkoordinaten (µm).
    "source": [-3.7, 2.7],
    "detector": [3.4, 2.25],
}

_proxies = []  # Event-Proxies müssen während der gesamten Laufzeit existieren.


def by_id(element_id):
    return document.getElementById(element_id)


interaction_hint = by_id("interaction-hint")
loading_status = by_id("py-status")

wavelength_slider = by_id("wavelength-slider")
wavelength_readout = by_id("wavelength-readout")
color_preview = by_id("color-preview")
color_name = by_id("color-name")

thickness_slider = by_id("thickness-slider")
thickness_readout = by_id("thickness-readout")
index_slider = by_id("index-slider")
index_readout = by_id("index-readout")
compare_toggle = by_id("compare-toggle")
compare_controls = by_id("compare-controls")
compare_wavelength_slider = by_id("compare-wavelength-slider")
compare_wavelength_readout = by_id("compare-wavelength-readout")

segment_slider = by_id("segment-slider")
segment_readout = by_id("segment-readout")
classic_toggle = by_id("classic-toggle")
path_graph_toggle = by_id("path-graph-toggle")

slit_select = by_id("slit-select")
slit_width_slider = by_id("slit-width-slider")
slit_width_readout = by_id("slit-width-readout")
slit_distance_controls = by_id("slit-distance-controls")
slit_distance_slider = by_id("slit-distance-slider")
slit_distance_readout = by_id("slit-distance-readout")
angle_slider = by_id("angle-slider")
angle_readout = by_id("angle-readout")
slit_segments_slider = by_id("slit-segments-slider")
slit_segments_readout = by_id("slit-segments-readout")
separate_row = by_id("separate-row")
separate_slits_toggle = by_id("separate-slits-toggle")

formula_toggle = by_id("formula-toggle")
formula_panel = by_id("formula-panel")
formula_title = by_id("formula-title")
formula_model_note = by_id("formula-model-note")
formula_content = by_id("formula-content")

readout_labels = [by_id(f"readout-label-{i}") for i in range(1, 5)]
readout_values = [by_id(f"readout-value-{i}") for i in range(1, 5)]


# =============================================================================
# Allgemeine Mathematik und Farbfunktionen
# =============================================================================

TAU = 2.0 * math.pi


def clamp(value, lower, upper):
    return max(lower, min(upper, value))


def fmt(value, digits=2):
    """Kurze Anzeigen in deutscher Dezimalschreibweise."""
    return f"{value:.{digits}f}".replace(".", ",")


def wavelength_nm():
    return float(wavelength_slider.value)


def wavelength_um():
    return wavelength_nm() / 1000.0


def phase_mod(phi):
    return phi % TAU


def complex_sum(values):
    total = 0j
    for value in values:
        total += value
    return total


def sinc(value):
    """sin(x)/x mit stabilem Grenzwert bei x = 0."""
    if abs(value) < 1e-10:
        return 1.0
    return math.sin(value) / value


def mix(a, b, t):
    return round(a + (b - a) * t)


def interpolate_rgb(c1, c2, t):
    t = clamp(t, 0.0, 1.0)
    return tuple(mix(c1[i], c2[i], t) for i in range(3))


def rgb_string(rgb, alpha=None):
    if alpha is None:
        return f"rgb({rgb[0]}, {rgb[1]}, {rgb[2]})"
    return f"rgba({rgb[0]}, {rgb[1]}, {rgb[2]}, {alpha})"


def wavelength_to_rgb_and_name(value):
    """
    Qualitative sRGB-Näherung. Bildschirmfarben sind keine exakte Wiedergabe
    monochromatischen Lichts, genügen hier aber zur eindeutigen Zuordnung.
    """
    anchors = [
        (380, (108, 45, 190), "violett"),
        (440, (48, 78, 230), "blau"),
        (490, (25, 170, 213), "cyan"),
        (520, (42, 190, 93), "grün"),
        (570, (216, 205, 34), "gelb"),
        (600, (246, 139, 32), "orange"),
        (650, (224, 55, 45), "rot"),
        (740, (139, 25, 40), "dunkelrot"),
    ]
    value = clamp(value, anchors[0][0], anchors[-1][0])
    for index in range(len(anchors) - 1):
        left, right = anchors[index], anchors[index + 1]
        if left[0] <= value <= right[0]:
            t = (value - left[0]) / (right[0] - left[0])
            rgb = interpolate_rgb(left[1], right[1], t)
            # Der Farbname folgt dem nächstgelegenen Stützpunkt.
            name = left[2] if t < 0.5 else right[2]
            return rgb, name
    return anchors[-1][1], anchors[-1][2]


def current_rgb():
    return wavelength_to_rgb_and_name(wavelength_nm())[0]


# =============================================================================
# Wiederverwendbare Canvas-Werkzeuge
# =============================================================================

INK = "#172033"
MUTED = "#68778d"
LINE = "#dce4ef"
SOFT = "#f7f9fc"
ACCENT = "#4257ff"
ACCENT_DARK = "#2638c8"
RESULT = "#151a2d"


def panel(rect, title, suffix=""):
    x, y, w, h = rect
    ctx.fillStyle = "#ffffff"
    ctx.fillRect(x, y, w, h)
    ctx.strokeStyle = LINE
    ctx.lineWidth = 1
    ctx.strokeRect(x + 0.5, y + 0.5, w - 1, h - 1)
    ctx.fillStyle = INK
    ctx.font = "800 16px Inter, system-ui, sans-serif"
    ctx.fillText(title, x + 18, y + 27)
    if suffix:
        ctx.fillStyle = MUTED
        ctx.font = "600 12px Inter, system-ui, sans-serif"
        width = ctx.measureText(suffix).width
        ctx.fillText(suffix, x + w - 18 - width, y + 26)


def line(x1, y1, x2, y2, color=INK, width=1.5, alpha=1.0):
    ctx.save()
    ctx.globalAlpha = alpha
    ctx.strokeStyle = color
    ctx.lineWidth = width
    ctx.beginPath()
    ctx.moveTo(x1, y1)
    ctx.lineTo(x2, y2)
    ctx.stroke()
    ctx.restore()


def dot(x, y, radius, color, stroke="#ffffff", stroke_width=2):
    ctx.beginPath()
    ctx.arc(x, y, radius, 0, TAU)
    ctx.fillStyle = color
    ctx.fill()
    if stroke_width:
        ctx.strokeStyle = stroke
        ctx.lineWidth = stroke_width
        ctx.stroke()


def label(text, x, y, color=MUTED, size=12, weight=650, align="left"):
    ctx.fillStyle = color
    ctx.font = f"{weight} {size}px Inter, system-ui, sans-serif"
    ctx.textAlign = align
    ctx.fillText(text, x, y)
    ctx.textAlign = "left"


def arrow(x1, y1, x2, y2, color=ACCENT, width=3, head=9, alpha=1.0):
    """Gerichteter Pfeil; identisch für Strahlenmarkierung und Zeiger."""
    angle = math.atan2(y2 - y1, x2 - x1)
    ctx.save()
    ctx.globalAlpha = alpha
    ctx.strokeStyle = color
    ctx.fillStyle = color
    ctx.lineWidth = width
    ctx.lineCap = "round"
    ctx.beginPath()
    ctx.moveTo(x1, y1)
    ctx.lineTo(x2, y2)
    ctx.stroke()
    ctx.beginPath()
    ctx.moveTo(x2, y2)
    ctx.lineTo(x2 - head * math.cos(angle - 0.48), y2 - head * math.sin(angle - 0.48))
    ctx.lineTo(x2 - head * math.cos(angle + 0.48), y2 - head * math.sin(angle + 0.48))
    ctx.closePath()
    ctx.fill()
    ctx.restore()


def chart_axes(rect, x_label, y_label, y_ticks=None):
    x, y, w, h = rect
    left, right = x + 62, x + w - 22
    top, bottom = y + 48, y + h - 42
    ctx.strokeStyle = LINE
    ctx.lineWidth = 1
    if y_ticks:
        for value, text_value in y_ticks:
            py = bottom - value * (bottom - top)
            line(left, py, right, py, LINE, 1)
            label(text_value, left - 10, py + 4, MUTED, 11, 600, "right")
    line(left, bottom, right, bottom, MUTED, 1.2)
    line(left, top, left, bottom, MUTED, 1.2)
    label(x_label, (left + right) / 2, y + h - 13, MUTED, 12, 700, "center")
    label(y_label, left, y + 39, MUTED, 12, 700)
    return left, top, right, bottom


def polyline(points, color, width=2.2, alpha=1.0):
    if not points:
        return
    ctx.save()
    ctx.globalAlpha = alpha
    ctx.strokeStyle = color
    ctx.lineWidth = width
    ctx.lineJoin = "round"
    ctx.beginPath()
    ctx.moveTo(points[0][0], points[0][1])
    for px, py in points[1:]:
        ctx.lineTo(px, py)
    ctx.stroke()
    ctx.restore()


def draw_phasor_axes(rect):
    x, y, w, h = rect
    cx, cy = x + w / 2, y + h / 2 + 10
    line(x + 34, cy, x + w - 25, cy, LINE, 1)
    line(cx, y + 48, cx, y + h - 25, LINE, 1)
    label("Re", x + w - 32, cy - 8, MUTED, 11, 700)
    label("Im", cx + 8, y + 58, MUTED, 11, 700)
    return cx, cy


def draw_phasor_chain(values, rect, color, highlight=None, result_color=RESULT):
    """
    Zeichnet eine Kopf-an-Schwanz-Kette und passt ihre Skalierung automatisch
    an den verfügbaren Bereich an. So bleiben auch viele Spiegelbeiträge lesbar.
    """
    x, y, w, h = rect
    sums = [0j]
    for value in values:
        sums.append(sums[-1] + value)

    re_values = [z.real for z in sums] + [0.0]
    im_values = [z.imag for z in sums] + [0.0]
    span_re = max(re_values) - min(re_values)
    span_im = max(im_values) - min(im_values)
    span = max(span_re, span_im, 0.35)
    scale = min((w - 88) / span, (h - 104) / span)

    center_re = (max(re_values) + min(re_values)) / 2
    center_im = (max(im_values) + min(im_values)) / 2
    cx = x + w / 2 - center_re * scale
    cy = y + h / 2 + 15 + center_im * scale

    # Dezente Bezugsachsen durch den Ursprung der komplexen Ebene.
    line(x + 24, cy, x + w - 24, cy, LINE, 1)
    line(cx, y + 48, cx, y + h - 22, LINE, 1)

    for index, value in enumerate(values):
        start = sums[index]
        end = sums[index + 1]
        selected = index == highlight
        arrow(
            cx + start.real * scale,
            cy - start.imag * scale,
            cx + end.real * scale,
            cy - end.imag * scale,
            ACCENT_DARK if selected else color,
            3.8 if selected else 1.7,
            8 if selected else 5,
            1.0 if selected else 0.72,
        )

    result = sums[-1]
    arrow(cx, cy, cx + result.real * scale, cy - result.imag * scale,
          result_color, 4.2, 11, 1.0)
    dot(cx, cy, 3.4, result_color, stroke_width=0)
    return result


def clear_canvas():
    ctx.clearRect(0, 0, WIDTH, HEIGHT)
    ctx.fillStyle = "#f9fbfe"
    ctx.fillRect(0, 0, WIDTH, HEIGHT)


# =============================================================================
# Versuch 1: Dünne Glasschicht
# =============================================================================

def film_values(lam=None, thickness=None, refractive_index=None):
    """Zwei gleich lange Zeiger mit Reflexionsphasensprung an Luft -> Glas."""
    lam = wavelength_nm() if lam is None else lam
    thickness = float(thickness_slider.value) if thickness is None else thickness
    refractive_index = float(index_slider.value) if refractive_index is None else refractive_index
    delta_phi = 4.0 * math.pi * refractive_index * thickness / lam + math.pi
    z1 = complex(0.2, 0.0)
    z2 = 0.2 * complex(math.cos(delta_phi), math.sin(delta_phi))
    total = z1 + z2
    return delta_phi, z1, z2, total, abs(total) ** 2


def draw_film_geometry():
    x, y, w, h = GEOMETRY
    panel(GEOMETRY, "Optischer Aufbau", "senkrechter Einfall")
    rgb = current_rgb()
    color = rgb_string(rgb)
    d = float(thickness_slider.value)
    layer_height = 42 + (d / 1200.0) * 142
    top = y + 146
    bottom = top + layer_height

    # Transparente Schicht mit klar getrennten Grenzflächen.
    ctx.fillStyle = "rgba(104, 169, 225, 0.18)"
    ctx.fillRect(x + 65, top, w - 130, layer_height)
    line(x + 65, top, x + w - 65, top, "#6b8cac", 2)
    line(x + 65, bottom, x + w - 65, bottom, "#6b8cac", 2)
    label("Luft", x + 78, top - 12, MUTED, 12, 700)
    label(f"Glas  n = {fmt(float(index_slider.value), 2)}", x + 78, top + 25, MUTED, 12, 700)

    # Die beiden Beiträge werden nebeneinander dargestellt. Innerhalb jedes
    # Beitrags läuft der Strahl bei normalem Einfall senkrecht und wird auf
    # demselben Weg zurückgeführt.
    ray_x1 = x + 285
    ray_x2 = x + 420
    arrow(ray_x1, y + 65, ray_x1, top - 3, color, 3.2, 10)
    arrow(ray_x1, top - 3, ray_x1, y + 72, color, 3.2, 10, 0.72)
    label("z₁", ray_x1 - 19, y + 88, color, 13, 850)

    arrow(ray_x2, y + 65, ray_x2, top - 3, color, 3.2, 10)
    line(ray_x2, top, ray_x2, bottom, color, 3.2)
    arrow(ray_x2, bottom, ray_x2, top + 5, color, 3.2, 10, 0.72)
    arrow(ray_x2, top - 5, ray_x2, y + 72, color, 3.2, 10, 0.72)
    label("z₂", ray_x2 + 17, y + 88, color, 13, 850)

    # Maßlinie für d.
    bx = x + w - 95
    line(bx, top, bx, bottom, MUTED, 1.4)
    line(bx - 7, top, bx + 7, top, MUTED, 1.4)
    line(bx - 7, bottom, bx + 7, bottom, MUTED, 1.4)
    label("d", bx + 12, (top + bottom) / 2 + 4, INK, 14, 800)


def draw_film_phasors():
    panel(PHASOR, "Zeigeraddition")
    delta_phi, z1, z2, total, _ = film_values()
    x, y, w, h = PHASOR
    cx, cy = draw_phasor_axes(PHASOR)
    scale = 520
    p1 = (cx + z1.real * scale, cy - z1.imag * scale)
    p2 = (p1[0] + z2.real * scale, p1[1] - z2.imag * scale)
    color = rgb_string(current_rgb())
    arrow(cx, cy, p1[0], p1[1], color, 4, 11)
    arrow(p1[0], p1[1], p2[0], p2[1], color, 4, 11, 0.82)
    arrow(cx, cy, cx + total.real * scale, cy - total.imag * scale, RESULT, 4.5, 12)
    label("E₁", (cx + p1[0]) / 2, cy - 12, color, 13, 850, "center")
    label("E₁", (cx + p1[0]) / 2, cy - 12,
          color, 13, 850, "center")
    label("E₂", (p1[0] + p2[0]) / 2,
          (p1[1] + p2[1]) / 2 - 11,
          color, 13, 850, "center")
    label("E", cx + total.real * scale + 10,
          cy - total.imag * scale - 8,
          RESULT, 14, 900)


def draw_film_graph():
    panel(GRAPH, "Reflexionsgrad", "R(d)")
    left, top, right, bottom = chart_axes(
        GRAPH, "Schichtdicke d in nm", "R", [(0, "0 %"), (0.5, "8 %"), (1, "16 %")]
    )
    max_d = 1200.0
    lam = wavelength_nm()
    rgb = current_rgb()

    def curve_points(curve_lam):
        points = []
        for index in range(361):
            d = max_d * index / 360
            reflection = film_values(lam=curve_lam, thickness=d)[4]
            px = left + (d / max_d) * (right - left)
            py = bottom - (reflection / 0.16) * (bottom - top)
            points.append((px, py))
        return points

    polyline(curve_points(lam), rgb_string(rgb), 3)
    label("0", left, bottom + 18, MUTED, 11, 600, "center")
    label("600", (left + right) / 2, bottom + 18, MUTED, 11, 600, "center")
    label("1200", right, bottom + 18, MUTED, 11, 600, "center")

    if compare_toggle.checked:
        lam2 = float(compare_wavelength_slider.value)
        rgb2 = wavelength_to_rgb_and_name(lam2)[0]
        polyline(curve_points(lam2), rgb_string(rgb2), 2.3, 0.85)
        label(f"λ₂ = {int(lam2)} nm", right - 8, top + 18, rgb_string(rgb2), 12, 800, "right")

    d = float(thickness_slider.value)
    reflection = film_values()[4]
    px = left + (d / max_d) * (right - left)
    py = bottom - (reflection / 0.16) * (bottom - top)
    line(px, top, px, bottom, rgb_string(rgb), 1.2, 0.35)
    dot(px, py, 6, rgb_string(rgb))


def draw_film():
    draw_film_geometry()
    draw_film_phasors()
    draw_film_graph()


# =============================================================================
# Versuch 2: Spiegel und stationäre Phase
# =============================================================================

MIRROR_X_MIN = -6.0
MIRROR_X_MAX = 6.0


def mirror_to_canvas(model_x, model_height):
    """Modellkoordinaten (µm) -> Pixel im Geometriefenster."""
    gx, gy, gw, gh = GEOMETRY
    px = gx + 62 + (model_x - MIRROR_X_MIN) / (MIRROR_X_MAX - MIRROR_X_MIN) * (gw - 124)
    mirror_y = gy + gh - 58
    py = mirror_y - model_height * 72
    return px, py


def canvas_to_mirror(px, py):
    gx, gy, gw, gh = GEOMETRY
    model_x = MIRROR_X_MIN + (px - gx - 62) / (gw - 124) * (MIRROR_X_MAX - MIRROR_X_MIN)
    mirror_y = gy + gh - 58
    model_h = (mirror_y - py) / 72
    return clamp(model_x, -5.6, 5.6), clamp(model_h, 0.45, 3.55)


def mirror_segments():
    count = int(float(segment_slider.value))
    step = (MIRROR_X_MAX - MIRROR_X_MIN) / count
    return [MIRROR_X_MIN + (i + 0.5) * step for i in range(count)]


def mirror_path_length(x):
    qx, qh = state["source"]
    dx, dh = state["detector"]
    return math.hypot(x - qx, qh) + math.hypot(dx - x, dh)


def classic_reflection_x():
    qx, qh = state["source"]
    dx, dh = state["detector"]
    return (qx * dh + dx * qh) / (qh + dh)


def mirror_phasors():
    xs = mirror_segments()
    reference = min(mirror_path_length(x) for x in xs)
    k = TAU / wavelength_um()
    amplitude = 1.0 / len(xs)
    values = []
    for x in xs:
        phase = k * (mirror_path_length(x) - reference)
        values.append(amplitude * complex(math.cos(phase), math.sin(phase)))
    return xs, values


def draw_mirror_geometry():
    panel(GEOMETRY, "Optischer Aufbau", "Quelle und Detektor ziehen")
    gx, gy, gw, gh = GEOMETRY
    mirror_y = gy + gh - 58
    x_left = mirror_to_canvas(MIRROR_X_MIN, 0)[0]
    x_right = mirror_to_canvas(MIRROR_X_MAX, 0)[0]
    line(x_left, mirror_y, x_right, mirror_y, "#263a55", 5)
    color = rgb_string(current_rgb())
    xs, _ = mirror_phasors()
    source_px = mirror_to_canvas(*state["source"])
    detector_px = mirror_to_canvas(*state["detector"])

    # Alle diskreten Wegbeiträge. Der überfahrene Beitrag wird hervorgehoben.
    for index, x_value in enumerate(xs):
        mirror_px = mirror_to_canvas(x_value, 0)
        selected = index == state["hover_segment"]
        width = 2.7 if selected else 1.0
        alpha = 0.95 if selected else 0.16
        line(source_px[0], source_px[1], mirror_px[0], mirror_px[1], color, width, alpha)
        line(mirror_px[0], mirror_px[1], detector_px[0], detector_px[1], color, width, alpha)
        if selected:
            dot(mirror_px[0], mirror_px[1], 5, ACCENT_DARK)

    if classic_toggle.checked:
        star = classic_reflection_x()
        star_px = mirror_to_canvas(star, 0)
        line(source_px[0], source_px[1], star_px[0], star_px[1], RESULT, 3.0, 0.8)
        line(star_px[0], star_px[1], detector_px[0], detector_px[1], RESULT, 3.0, 0.8)
        dot(star_px[0], star_px[1], 5, RESULT)
        label("klassisch", star_px[0], mirror_y + 23, RESULT, 11, 800, "center")

    dot(source_px[0], source_px[1], 10, color)
    dot(detector_px[0], detector_px[1], 10, RESULT)
    label("Q", source_px[0], source_px[1] - 16, color, 14, 900, "center")
    label("D", detector_px[0], detector_px[1] - 16, RESULT, 14, 900, "center")
    label("Spiegel", x_left, mirror_y + 23, MUTED, 11, 700)


def draw_mirror_phasor_panel():
    panel(PHASOR, "Zeigerkette")
    _, values = mirror_phasors()
    draw_phasor_chain(values, PHASOR, rgb_string(current_rgb()), state["hover_segment"])


def draw_mirror_graph():
    if path_graph_toggle.checked:
        panel(GRAPH, "Optische Weglänge", "stationärer Bereich")
        xs = [MIRROR_X_MIN + i * (MIRROR_X_MAX - MIRROR_X_MIN) / 360 for i in range(361)]
        lengths = [mirror_path_length(x) for x in xs]
        min_l, max_l = min(lengths), max(lengths)
        left, top, right, bottom = chart_axes(GRAPH, "Spiegelposition x in µm", "L(x)")
        points = []
        for x_value, length_value in zip(xs, lengths):
            px = left + (x_value - MIRROR_X_MIN) / (MIRROR_X_MAX - MIRROR_X_MIN) * (right - left)
            py = bottom - (length_value - min_l) / max(max_l - min_l, 1e-9) * (bottom - top)
            points.append((px, py))
        polyline(points, ACCENT, 3)
        star = classic_reflection_x()
        star_l = mirror_path_length(star)
        px = left + (star - MIRROR_X_MIN) / (MIRROR_X_MAX - MIRROR_X_MIN) * (right - left)
        py = bottom - (star_l - min_l) / max(max_l - min_l, 1e-9) * (bottom - top)
        dot(px, py, 6, RESULT)
        label("dL/dx = 0", px + 12, py - 10, RESULT, 12, 850)
        label("−6", left, bottom + 18, MUTED, 11, 600, "center")
        label("0", (left + right) / 2, bottom + 18, MUTED, 11, 600, "center")
        label("6", right, bottom + 18, MUTED, 11, 600, "center")
    else:
        panel(GRAPH, "Gesamtbeitrag", "Betragsquadrat")
        _, values = mirror_phasors()
        result = complex_sum(values)
        intensity = abs(result) ** 2
        gx, gy, gw, gh = GRAPH
        bar_left, bar_right = gx + 145, gx + gw - 145
        bar_y = gy + 154
        ctx.fillStyle = "#e8edf5"
        ctx.fillRect(bar_left, bar_y, bar_right - bar_left, 28)
        ctx.fillStyle = rgb_string(current_rgb())
        ctx.fillRect(bar_left, bar_y, (bar_right - bar_left) * intensity, 28)
        label("0", bar_left, bar_y + 51, MUTED, 11, 600, "center")
        label("1", bar_right, bar_y + 51, MUTED, 11, 600, "center")
        label(f"|E|² = {fmt(intensity, 3)}", (bar_left + bar_right) / 2,
              bar_y - 28, INK, 22, 850, "center")
        label("L(x)-Diagramm in der Steuerung einblenden", (bar_left + bar_right) / 2,
              gy + gh - 36, MUTED, 12, 650, "center")


def draw_mirror():
    draw_mirror_geometry()
    draw_mirror_phasor_panel()
    draw_mirror_graph()


# =============================================================================
# Versuch 3: Einzel- und Doppelspalt in Fraunhofer-Näherung
# =============================================================================

def diffraction_type():
    return slit_select.value


def diffraction_positions():
    """
    Diskretisierung der offenen Bereiche in µm. Beim Doppelspalt erhält jeder
    Spalt gleich viele Beiträge; die Gesamtamplitude ist auf θ = 0 normiert.
    """
    total_count = int(float(slit_segments_slider.value))
    width = float(slit_width_slider.value)
    if diffraction_type() == "single":
        return [(-width / 2 + (i + 0.5) * width / total_count, 0)
                for i in range(total_count)]

    count_per_slit = max(2, total_count // 2)
    distance = float(slit_distance_slider.value)
    positions = []
    for slit_index, center in enumerate((-distance / 2, distance / 2)):
        for i in range(count_per_slit):
            positions.append((center - width / 2 + (i + 0.5) * width / count_per_slit,
                              slit_index))
    return positions


def diffraction_phasors(theta_deg=None):
    theta_deg = float(angle_slider.value) if theta_deg is None else theta_deg
    theta = math.radians(theta_deg)
    positions = diffraction_positions()
    amplitude = 1.0 / len(positions)
    k = TAU / wavelength_um()
    values = []
    for x_value, slit_index in positions:
        phase = k * x_value * math.sin(theta)
        values.append((amplitude * complex(math.cos(phase), math.sin(phase)), slit_index))
    return positions, values


def diffraction_intensity(theta_deg):
    theta = math.radians(theta_deg)
    lam = wavelength_um()
    width = float(slit_width_slider.value)
    beta = math.pi * width * math.sin(theta) / lam
    envelope = sinc(beta) ** 2
    if diffraction_type() == "single":
        return envelope
    distance = float(slit_distance_slider.value)
    alpha = math.pi * distance * math.sin(theta) / lam
    return envelope * math.cos(alpha) ** 2


def aperture_scale():
    """Skalierung, die auch große Doppelspaltabstände im Fenster hält."""
    width = float(slit_width_slider.value)
    full_extent = width
    if diffraction_type() == "double":
        full_extent += float(slit_distance_slider.value)
    return min(3.9, 220.0 / max(full_extent, 1.0))


def diffraction_apertures_canvas():
    """Liefert die vertikalen Öffnungsintervalle im Geometriefenster."""
    center_y = GEOMETRY[1] + GEOMETRY[3] / 2 + 8
    width = float(slit_width_slider.value)
    scale = aperture_scale()
    if diffraction_type() == "single":
        return [(center_y - width * scale / 2, center_y + width * scale / 2)]
    distance = float(slit_distance_slider.value)
    return [
        (center_y + (-distance / 2 - width / 2) * scale,
         center_y + (-distance / 2 + width / 2) * scale),
        (center_y + (distance / 2 - width / 2) * scale,
         center_y + (distance / 2 + width / 2) * scale),
    ]


def draw_diffraction_geometry():
    panel(GEOMETRY, "Optischer Aufbau", "Detektor am Schirm ziehen")
    gx, gy, gw, gh = GEOMETRY
    color = rgb_string(current_rgb())
    aperture_x = gx + 285
    screen_x = gx + gw - 65
    center_y = gy + gh / 2 + 8
    screen_top, screen_bottom = gy + 60, gy + gh - 35

    # Einfallende ebene Wellenfronten und Ausbreitungsrichtung.
    for offset in (0, 34, 68):
        x_wave = gx + 70 + offset
        line(x_wave, gy + 72, x_wave, gy + gh - 48, color, 2, 0.45)
    arrow(gx + 80, center_y, aperture_x - 18, center_y, color, 3, 10)

    # Blende als zwei bzw. drei massive Abschnitte um die Öffnungen.
    intervals = sorted(diffraction_apertures_canvas())
    current_y = screen_top
    ctx.fillStyle = "#263a55"
    for opening_top, opening_bottom in intervals:
        ctx.fillRect(aperture_x - 7, current_y, 14, max(0, opening_top - current_y))
        current_y = opening_bottom
    ctx.fillRect(aperture_x - 7, current_y, 14, max(0, screen_bottom - current_y))
    label("Blende", aperture_x, screen_bottom + 22, MUTED, 11, 700, "center")

    # Der Schirmpunkt wird direkt aus dem Beobachtungswinkel abgebildet.
    line(screen_x, screen_top, screen_x, screen_bottom, "#263a55", 5)
    theta_deg = float(angle_slider.value)
    detector_y = center_y - theta_deg * 12.2
    detector_y = clamp(detector_y, screen_top + 4, screen_bottom - 4)

    # Nur eine überschaubare Teilmenge der vielen Beiträge als Wege zeichnen.
    positions, _ = diffraction_phasors()
    position_scale = aperture_scale()
    stride = max(1, len(positions) // 16)
    for index, (position, _) in enumerate(positions):
        if index % stride != 0 and index != len(positions) - 1:
            continue
        slit_y = center_y + position * position_scale
        line(aperture_x + 7, slit_y, screen_x, detector_y, color, 1.0, 0.20)

    dot(screen_x, detector_y, 8, color)
    label("θ", aperture_x + 55, center_y - 9, INK, 14, 850)
    line(aperture_x + 8, center_y, screen_x, center_y, LINE, 1)
    label("Schirm", screen_x, screen_bottom + 22, MUTED, 11, 700, "center")


def draw_diffraction_phasors():
    suffix = "zwei Teilresultierende" if (
        diffraction_type() == "double" and separate_slits_toggle.checked
    ) else "diskrete Beiträge"
    panel(PHASOR, "Zeigerkette", suffix)
    _, tagged = diffraction_phasors()
    values = [item[0] for item in tagged]
    result = draw_phasor_chain(values, PHASOR, rgb_string(current_rgb()))

    if diffraction_type() == "double" and separate_slits_toggle.checked:
        sum_1 = complex_sum(item[0] for item in tagged if item[1] == 0)
        sum_2 = complex_sum(item[0] for item in tagged if item[1] == 1)
        x, y, w, h = PHASOR
        label(f"|E₁| = {fmt(abs(sum_1), 2)}", x + 18, y + h - 33, ACCENT, 11, 800)
        label(f"|E₂| = {fmt(abs(sum_2), 2)}", x + 112, y + h - 33, ACCENT_DARK, 11, 800)
        label(f"|E| = {fmt(abs(result), 2)}", x + w - 18, y + h - 33, RESULT, 11, 850, "right")


def draw_diffraction_graph():
    title = "Fraunhofer-Beugung – Fernfeldnäherung"
    panel(GRAPH, title, "I(θ) / I(0)")
    left, top, right, bottom = chart_axes(
        GRAPH, "Beobachtungswinkel θ", "relative Intensität", [(0, "0"), (0.5, "0,5"), (1, "1")]
    )
    points = []
    for index in range(501):
        theta = -10.0 + 20.0 * index / 500
        intensity = diffraction_intensity(theta)
        px = left + index / 500 * (right - left)
        py = bottom - intensity * (bottom - top)
        points.append((px, py))
    polyline(points, rgb_string(current_rgb()), 3)
    for theta, tick in ((-10, "−10°"), (-5, "−5°"), (0, "0°"), (5, "5°"), (10, "10°")):
        px = left + (theta + 10) / 20 * (right - left)
        label(tick, px, bottom + 18, MUTED, 11, 600, "center")

    theta = float(angle_slider.value)
    intensity = diffraction_intensity(theta)
    px = left + (theta + 10) / 20 * (right - left)
    py = bottom - intensity * (bottom - top)
    line(px, top, px, bottom, rgb_string(current_rgb()), 1.2, 0.35)
    dot(px, py, 6, rgb_string(current_rgb()))


def draw_diffraction():
    draw_diffraction_geometry()
    draw_diffraction_phasors()
    draw_diffraction_graph()


# =============================================================================
# Anzeigen, Formelmodus und Szenenwechsel
# =============================================================================

def set_readouts(labels, values):
    for index in range(4):
        readout_labels[index].textContent = labels[index]
        readout_values[index].textContent = values[index]


def update_readouts():
    experiment = state["experiment"]
    if experiment == "film":
        delta_phi, _, _, total, reflection = film_values()
        set_readouts(
            ["Dicke d", "Phasendifferenz", "Resultierende", "Reflexion R"],
            [f"{int(float(thickness_slider.value))} nm",
             f"{fmt(phase_mod(delta_phi), 2)} rad",
             fmt(abs(total), 3),
             f"{fmt(reflection * 100, 1)} %"],
        )
    elif experiment == "mirror":
        xs, values = mirror_phasors()
        result = complex_sum(values)
        star = classic_reflection_x()
        hover = state["hover_segment"]
        selected = "–" if hover is None else f"x = {fmt(xs[hover], 2)} µm"
        set_readouts(
            ["Beiträge", "Ausgewählter Bereich", "Stationärer Punkt", "Betragsquadrat |E|²"],
            [str(len(xs)), selected, f"x = {fmt(star, 2)} µm", fmt(abs(result) ** 2, 3)],
        )
    else:
        theta = float(angle_slider.value)
        _, tagged = diffraction_phasors()
        result = complex_sum(item[0] for item in tagged)
        set_readouts(
            ["Öffnung", "Winkel θ", "Resultierende", "Relative Intensität"],
            ["Einzelspalt" if diffraction_type() == "single" else "Doppelspalt",
             f"{fmt(theta, 2)}°", fmt(abs(result), 3), fmt(diffraction_intensity(theta), 3)],
        )


def formula_card(title, formula, value=""):
    value_html = f'<p class="formula-value">{value}</p>' if value else ""
    return f'<article class="formula-card"><h3>{title}</h3><code>{formula}</code>{value_html}</article>'


def update_formula_panel():
    experiment = state["experiment"]
    if experiment == "film":
        delta_phi, _, _, total, reflection = film_values()
        formula_title.textContent = "Dünne Glasschicht"
        formula_model_note.textContent = "Zwei Beiträge, senkrechter Einfall, keine Mehrfachreflexionen."
        formula_content.innerHTML = "".join([
            formula_card("Optischer Weg", "ΔL<sub>opt</sub> = 2nd",
                         f"2 · {fmt(float(index_slider.value), 2)} · {int(float(thickness_slider.value))} nm"),
            formula_card("Phasendifferenz", "Δφ = 4πnd / λ + π",
                         f"Δφ mod 2π = {fmt(phase_mod(delta_phi), 2)} rad"),
            formula_card("Zeigersumme", "E = 0,2 + 0,2 · e<sup>iΔφ</sup>",
                         f"E|E| = {fmt(abs(total), 3)}"),
            formula_card("Reflexion", "R = |E|²", f"R = {fmt(reflection * 100, 1)} %"),
        ])
    elif experiment == "mirror":
        xs, values = mirror_phasors()
        result = complex_sum(values)
        formula_title.textContent = "Spiegel: alle Beiträge"
        formula_model_note.textContent = "Diskrete Spiegelbereiche mit gleichen Zeigerlängen."
        formula_content.innerHTML = "".join([
            formula_card("Weglänge", "L(x) = L<sub>Qx</sub> + L<sub>xD</sub>"),
            formula_card("Phase", "φ(x) = 2πL(x) / λ"),
            formula_card("Gesamtamplitude", "E = Σ A · e<sup>iφ(x)</sup>",
                         f"N = {len(xs)}, |E| = {fmt(abs(result), 3)}"),
            formula_card("Stationäre Phase", "dL / dx = 0  ⇒  α = β",
                         f"x<sub>stat</sub> = {fmt(classic_reflection_x(), 2)} µm"),
        ])
    else:
        theta = float(angle_slider.value)
        intensity = diffraction_intensity(theta)
        double = diffraction_type() == "double"
        formula_title.textContent = "Fraunhofer-Beugung – Fernfeldnäherung"
        formula_model_note.textContent = "Diskrete Zeiger; analytische Intensitätskurve."
        last_formula = (
            "I / I(0) = (sin β / β)² · cos² α"
            if double else "I / I(0) = (sin β / β)²"
        )
        last_value = f"I / I(0) = {fmt(intensity, 3)}"
        formula_content.innerHTML = "".join([
            formula_card("Phase eines Beitrags", "φ(x) = kx sin θ"),
            formula_card("Gesamtamplitude", "E(θ) ∝ ∫ e<sup>ikx sin θ</sup> dx"),
            formula_card("Hilfsgrößen", "β = πa sin θ / λ" + ("; α = πd sin θ / λ" if double else ""),
                         f"θ = {fmt(theta, 2)}°"),
            formula_card("Intensität", last_formula, last_value),
        ])


def sync_controls():
    lam = wavelength_nm()
    rgb, name = wavelength_to_rgb_and_name(lam)
    wavelength_readout.textContent = f"{int(lam)} nm"
    color_preview.style.background = rgb_string(rgb)
    color_name.textContent = name

    thickness_readout.textContent = f"{int(float(thickness_slider.value))} nm"
    index_readout.textContent = fmt(float(index_slider.value), 2)
    compare_wavelength_readout.textContent = f"{int(float(compare_wavelength_slider.value))} nm"
    compare_controls.classList.toggle("hidden", not compare_toggle.checked)

    segment_readout.textContent = str(int(float(segment_slider.value)))

    slit_width = float(slit_width_slider.value)
    is_double = diffraction_type() == "double"
    if is_double:
        # Zwei reale Spalte dürfen sich geometrisch nicht überlappen.
        minimum_distance = min(60.0, slit_width + 1.0)
        slit_distance_slider.min = f"{minimum_distance:.1f}"
        if float(slit_distance_slider.value) < minimum_distance:
            slit_distance_slider.value = f"{minimum_distance:.1f}"

    slit_width_readout.textContent = f"{fmt(slit_width, 1)} µm"
    slit_distance_readout.textContent = f"{fmt(float(slit_distance_slider.value), 1)} µm"
    angle_readout.textContent = f"{fmt(float(angle_slider.value), 2)}°"
    slit_segments_readout.textContent = str(int(float(slit_segments_slider.value)))
    slit_distance_controls.classList.toggle("hidden", not is_double)
    separate_row.classList.toggle("hidden", not is_double)


def draw():
    sync_controls()
    clear_canvas()
    experiment = state["experiment"]
    if experiment == "film":
        draw_film()
    elif experiment == "mirror":
        draw_mirror()
    else:
        draw_diffraction()
    update_readouts()
    if not formula_panel.classList.contains("hidden"):
        update_formula_panel()


SCENE_HINTS = {
    "film": "Variiere Schichtdicke und Brechungsindex.",
    "mirror": "Verschiebe Quelle oder Detektor; erkunde die Spiegelbereiche.",
    "diffraction": "Verschiebe den Beobachtungspunkt am Schirm.",
}


def switch_experiment(experiment):
    state["experiment"] = experiment
    state["hover_segment"] = None
    state["drag_target"] = None
    for button in document.querySelectorAll(".experiment-tab"):
        active = button.getAttribute("data-experiment") == experiment
        button.classList.toggle("active", active)
        button.setAttribute("aria-selected", "true" if active else "false")
    for section in document.querySelectorAll(".scene-controls"):
        section.classList.add("hidden")
    by_id(f"{experiment}-controls").classList.remove("hidden")
    interaction_hint.textContent = SCENE_HINTS[experiment]
    canvas.style.cursor = "grab" if experiment != "film" else "default"
    draw()


# =============================================================================
# Maus- und Touchinteraktion
# =============================================================================

def canvas_position(event):
    rect = canvas.getBoundingClientRect()
    return (
        (event.clientX - rect.left) * WIDTH / rect.width,
        (event.clientY - rect.top) * HEIGHT / rect.height,
    )


def point_distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def on_pointer_down(event):
    px, py = canvas_position(event)
    if state["experiment"] == "mirror":
        source_px = mirror_to_canvas(*state["source"])
        detector_px = mirror_to_canvas(*state["detector"])
        if point_distance((px, py), source_px) <= 18:
            state["drag_target"] = "source"
        elif point_distance((px, py), detector_px) <= 18:
            state["drag_target"] = "detector"
    elif state["experiment"] == "diffraction":
        # Im rechten Teil der Geometrieansicht wird der Schirmpunkt gegriffen.
        gx, gy, gw, gh = GEOMETRY
        if gx + gw - 105 <= px <= gx + gw and gy + 45 <= py <= gy + gh - 25:
            state["drag_target"] = "screen"
    if state["drag_target"]:
        canvas.setPointerCapture(event.pointerId)
        canvas.style.cursor = "grabbing"
        event.preventDefault()


def on_pointer_move(event):
    px, py = canvas_position(event)
    experiment = state["experiment"]
    if state["drag_target"] in ("source", "detector"):
        state[state["drag_target"]] = list(canvas_to_mirror(px, py))
        draw()
        return
    if state["drag_target"] == "screen":
        center_y = GEOMETRY[1] + GEOMETRY[3] / 2 + 8
        theta = clamp((center_y - py) / 12.2, -10.0, 10.0)
        angle_slider.value = f"{theta:.2f}"
        draw()
        return

    if experiment == "mirror":
        gx, gy, gw, gh = GEOMETRY
        if gx <= px <= gx + gw and gy + 45 <= py <= gy + gh:
            model_x, _ = canvas_to_mirror(px, py)
            xs = mirror_segments()
            nearest = min(range(len(xs)), key=lambda i: abs(xs[i] - model_x))
        else:
            nearest = None
        if nearest != state["hover_segment"]:
            state["hover_segment"] = nearest
            draw()


def on_pointer_up(event):
    if state["drag_target"]:
        state["drag_target"] = None
        canvas.style.cursor = "grab"
        try:
            canvas.releasePointerCapture(event.pointerId)
        except Exception:
            pass


def on_pointer_leave(event):
    if state["experiment"] == "mirror" and not state["drag_target"]:
        if state["hover_segment"] is not None:
            state["hover_segment"] = None
            draw()


# =============================================================================
# Event-Bindings und Initialisierung
# =============================================================================

def bind(element, event_name, handler):
    proxy = create_proxy(handler)
    _proxies.append(proxy)
    element.addEventListener(event_name, proxy)


def redraw_event(event):
    draw()


def tab_event(event):
    switch_experiment(event.currentTarget.getAttribute("data-experiment"))


def formula_event(event):
    opening = formula_panel.classList.contains("hidden")
    formula_panel.classList.toggle("hidden", not opening)
    formula_toggle.textContent = "Formelmodus ausblenden" if opening else "Formelmodus anzeigen"
    formula_toggle.setAttribute("aria-expanded", "true" if opening else "false")
    if opening:
        update_formula_panel()


for button in document.querySelectorAll(".experiment-tab"):
    bind(button, "click", tab_event)

for control in (
    wavelength_slider, thickness_slider, index_slider, compare_toggle,
    compare_wavelength_slider, segment_slider, classic_toggle, path_graph_toggle,
    slit_select, slit_width_slider, slit_distance_slider, angle_slider,
    slit_segments_slider, separate_slits_toggle,
):
    bind(control, "input", redraw_event)

bind(formula_toggle, "click", formula_event)
bind(canvas, "pointerdown", on_pointer_down)
bind(canvas, "pointermove", on_pointer_move)
bind(canvas, "pointerup", on_pointer_up)
bind(canvas, "pointercancel", on_pointer_up)
bind(canvas, "pointerleave", on_pointer_leave)

# Erst zeichnen, dann den Ladehinweis entfernen. Bleibt PyScript beim Laden
# hängen, bleibt die Statusmeldung sichtbar und verschwindet nicht irreführend.
switch_experiment("film")
loading_status.classList.add("hidden")
