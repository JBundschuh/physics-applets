# ================================================================
# Physik-Applet mit PyScript
# Thema: Elastischer und plastischer Stoß zweier Körper
# ================================================================
# Struktur:
# 1. DOM-Zugriff
# 2. Parameter und Modellzustand
# 3. Hilfsfunktionen
# 4. Physik
# 5. Darstellung
# 6. Interaktion
# 7. Zeitentwicklung: update(), draw(), request()
# ================================================================

from pyscript import document, window, when
from pyscript.ffi import create_proxy
import math


# ================================================================
# 1. DOM-Zugriff
# ================================================================

sim_canvas = document.getElementById("sim-canvas")
ctx = sim_canvas.getContext("2d")

mass_1_slider = document.getElementById("mass-1")
mass_1_value = document.getElementById("mass-1-value")

velocity_1_slider = document.getElementById("velocity-1")
velocity_1_value = document.getElementById("velocity-1-value")

mass_2_slider = document.getElementById("mass-2")
mass_2_value = document.getElementById("mass-2-value")

velocity_2_slider = document.getElementById("velocity-2")
velocity_2_value = document.getElementById("velocity-2-value")

restitution_slider = document.getElementById("restitution")
restitution_value = document.getElementById("restitution-value")

heat_colors_checkbox = document.getElementById("heat-colors")

start_button = document.getElementById("start-button")
reset_button = document.getElementById("reset-button")

p1_before_element = document.getElementById("p1-before")
p1_after_element = document.getElementById("p1-after")
p2_before_element = document.getElementById("p2-before")
p2_after_element = document.getElementById("p2-after")

p_before_element = document.getElementById("p-before")
p_after_element = document.getElementById("p-after")
delta_p_element = document.getElementById("delta-p")

e_before_element = document.getElementById("e-before")
e_after_element = document.getElementById("e-after")
e_diss_element = document.getElementById("e-diss")
delta_e_element = document.getElementById("delta-e")


# ================================================================
# 2. Parameter und Modellzustand
# ================================================================

MAX_DT = 0.035

GROUND_Y = 285
BLOCK_SIZE_FACTOR = 34.0

START_X_1 = 150.0
START_X_2 = 550.0

m1 = 3.0
m2 = 4.0
v1 = 120.0
v2 = -100.0
e = 1.0

block1 = {}
block2 = {}

laeuft = False
stoss_passiert = False
letzter_zeitpunkt = None

# Farbeffekt: 0 = blau, 1 = rot
dissipations_anteil = 0.0

# Auswertungsgrößen
p1_vor = None
p2_vor = None
p_vor = None
e_vor = None

p1_nach = None
p2_nach = None
p_nach = None
e_nach = None
e_diss = None


# ================================================================
# 3. Hilfsfunktionen
# ================================================================

def zahl_deutsch(wert, stellen=2):
    """
    Formatiert Zahlen mit Dezimalkomma.
    """
    if wert is None:
        return "—"

    if abs(wert) < 1e-10:
        wert = 0.0

    text = f"{wert:.{stellen}f}"
    return text.replace(".", ",")


def begrenze_wert(x, minimum, maximum):
    return max(minimum, min(maximum, x))


def mische_farben(farbe_a, farbe_b, anteil):
    """
    Lineare Mischung zweier RGB-Farben.
    """
    anteil = begrenze_wert(anteil, 0.0, 1.0)

    r = int(farbe_a[0] + anteil * (farbe_b[0] - farbe_a[0]))
    g = int(farbe_a[1] + anteil * (farbe_b[1] - farbe_a[1]))
    b = int(farbe_a[2] + anteil * (farbe_b[2] - farbe_a[2]))

    return f"rgb({r}, {g}, {b})"


def farbe_aus_dissipation(anteil):
    """
    Blau: keine dissipierte Energie
    Rot: maximale dissipierte Energie
    """
    blau = (37, 99, 235)
    rot = (220, 38, 38)
    return mische_farben(blau, rot, anteil)


def block_seitenlaenge(masse):
    """
    Gleiche Dichte in der 2D-Darstellung:

        sichtbare Fläche ∝ Masse

    Da die Blöcke quadratisch dargestellt werden, gilt:

        Seitenlänge ∝ sqrt(Masse)
    """
    return BLOCK_SIZE_FACTOR * math.sqrt(masse)


def lese_parameter_aus_ui():
    """
    Liest alle Sliderwerte in das Modell ein.
    """
    global m1, m2, v1, v2, e

    m1 = float(mass_1_slider.value)
    m2 = float(mass_2_slider.value)

    v1 = float(velocity_1_slider.value)
    v2 = -float(velocity_2_slider.value)

    e = float(restitution_slider.value)


def aktualisiere_slidertexte():
    mass_1_value.textContent = zahl_deutsch(m1, 1)
    mass_2_value.textContent = zahl_deutsch(m2, 1)

    velocity_1_value.textContent = zahl_deutsch(v1, 0)
    velocity_2_value.textContent = zahl_deutsch(v2, 0)

    restitution_value.textContent = zahl_deutsch(e, 2)


def setze_controls_aktiv(aktiv):
    """
    Nach Start werden alle Parameter gesperrt.
    Nach Reset werden sie wieder freigegeben.
    """
    mass_1_slider.disabled = not aktiv
    velocity_1_slider.disabled = not aktiv

    mass_2_slider.disabled = not aktiv
    velocity_2_slider.disabled = not aktiv

    restitution_slider.disabled = not aktiv
    heat_colors_checkbox.disabled = not aktiv

    start_button.disabled = not aktiv


def setze_startzustand():
    """
    Erzeugt die Blöcke aus den aktuellen Parametern.
    """
    global block1, block2
    global dissipations_anteil
    global p1_nach, p2_nach, p_nach, e_nach, e_diss

    s1 = block_seitenlaenge(m1)
    s2 = block_seitenlaenge(m2)

    block1 = {
        "x": START_X_1,
        "v": v1,
        "w": s1,
        "h": s1,
        "farbe": "#2563eb",
        "name": "Körper 1",
    }

    block2 = {
        "x": START_X_2,
        "v": v2,
        "w": s2,
        "h": s2,
        "farbe": "#16a34a",
        "name": "Körper 2",
    }

    dissipations_anteil = 0.0

    p1_nach = None
    p2_nach = None
    p_nach = None
    e_nach = None
    e_diss = None


def berechne_startwerte():
    """
    Berechnet Impuls und Energie vor dem Stoß.
    """
    global p1_vor, p2_vor, p_vor, e_vor

    p1_vor = m1 * v1
    p2_vor = m2 * v2
    p_vor = p1_vor + p2_vor

    e_vor = 0.5 * m1 * v1 ** 2 + 0.5 * m2 * v2 ** 2


def aktualisiere_auswertung():
    """
    Schreibt die aktuellen Auswertungsgrößen in das HTML.
    """
    p1_before_element.textContent = zahl_deutsch(p1_vor, 2)
    p2_before_element.textContent = zahl_deutsch(p2_vor, 2)
    p_before_element.textContent = zahl_deutsch(p_vor, 2)
    e_before_element.textContent = zahl_deutsch(e_vor, 2)

    p1_after_element.textContent = zahl_deutsch(p1_nach, 2)
    p2_after_element.textContent = zahl_deutsch(p2_nach, 2)
    p_after_element.textContent = zahl_deutsch(p_nach, 2)
    e_after_element.textContent = zahl_deutsch(e_nach, 2)
    e_diss_element.textContent = zahl_deutsch(e_diss, 2)

    if p_nach is None:
        delta_p_element.textContent = "—"
    else:
        delta_p_element.textContent = zahl_deutsch(p_nach - p_vor, 6)

    if e_diss is None:
        delta_e_element.textContent = "—"
    else:
        delta_e_element.textContent = zahl_deutsch(e_diss, 2)


def aktualisiere_parameter_und_startzustand():
    """
    Wird benutzt, solange die Simulation noch nicht gestartet ist.
    """
    lese_parameter_aus_ui()
    aktualisiere_slidertexte()
    setze_startzustand()
    berechne_startwerte()
    aktualisiere_auswertung()


# ================================================================
# 4. Physik
# ================================================================

def linke_kante(block):
    return block["x"] - block["w"] / 2


def rechte_kante(block):
    return block["x"] + block["w"] / 2


def kinetische_energie(masse, geschwindigkeit):
    return 0.5 * masse * geschwindigkeit ** 2


def berechne_stoss():
    """
    Berechnet den eindimensionalen Stoß mit Stoßzahl e.

    Annahmen:
        - Impulserhaltung gilt immer.
        - Die Stoßzahl e legt fest, wie stark der Stoß elastisch ist.
        - e = 1: vollkommen elastisch
        - e = 0: vollkommen plastisch
    """
    global stoss_passiert
    global p1_nach, p2_nach, p_nach, e_nach, e_diss
    global dissipations_anteil

    v1_alt = block1["v"]
    v2_alt = block2["v"]

    # Endgeschwindigkeiten für den 1D-Stoß mit Restitutionskoeffizient e
    v1_neu = (m1 * v1_alt + m2 * v2_alt - m2 * e * (v1_alt - v2_alt)) / (m1 + m2)
    v2_neu = (m1 * v1_alt + m2 * v2_alt + m1 * e * (v1_alt - v2_alt)) / (m1 + m2)

    block1["v"] = v1_neu
    block2["v"] = v2_neu

    p1_nach = m1 * v1_neu
    p2_nach = m2 * v2_neu
    p_nach = p1_nach + p2_nach

    e_nach = kinetische_energie(m1, v1_neu) + kinetische_energie(m2, v2_neu)
    e_diss = max(0.0, e_vor - e_nach)

    # Maximale Dissipation beim vollkommen plastischen Stoß
    reduzierte_masse = (m1 * m2) / (m1 + m2)
    e_diss_max = 0.5 * reduzierte_masse * (v1_alt - v2_alt) ** 2

    if e_diss_max > 0:
        dissipations_anteil = begrenze_wert(e_diss / e_diss_max, 0.0, 1.0)
    else:
        dissipations_anteil = 0.0

    stoss_passiert = True
    aktualisiere_auswertung()


def pruefe_stoss():
    """
    Prüft, ob die Blöcke kollidieren.

    Der Stoß wird genau einmal berechnet.
    """
    if stoss_passiert:
        return

    if rechte_kante(block1) >= linke_kante(block2):
        # Positionskorrektur: Blöcke sollen beim Stoß nicht ineinander stecken.
        ueberlappung = rechte_kante(block1) - linke_kante(block2)

        block1["x"] -= ueberlappung / 2
        block2["x"] += ueberlappung / 2

        berechne_stoss()


# ================================================================
# 5. Darstellung
# ================================================================

def zeichne_pfeil(x0, y0, laenge, farbe):
    """
    Zeichnet einen Geschwindigkeitspfeil.
    """
    if abs(laenge) < 1:
        return

    x1 = x0 + laenge
    richtung = 1 if laenge > 0 else -1

    ctx.strokeStyle = farbe
    ctx.fillStyle = farbe
    ctx.lineWidth = 3

    ctx.beginPath()
    ctx.moveTo(x0, y0)
    ctx.lineTo(x1, y0)
    ctx.stroke()

    ctx.beginPath()
    ctx.moveTo(x1, y0)
    ctx.lineTo(x1 - richtung * 10, y0 - 6)
    ctx.lineTo(x1 - richtung * 10, y0 + 6)
    ctx.closePath()
    ctx.fill()


def zeichne_block(block, masse, standardfarbe):
    """
    Zeichnet einen Block auf der Unterlage.
    """
    x = block["x"]
    w = block["w"]
    h = block["h"]

    y_oben = GROUND_Y - h

    if heat_colors_checkbox.checked and stoss_passiert:
        farbe = farbe_aus_dissipation(dissipations_anteil)
    else:
        farbe = standardfarbe

    # Block
    ctx.fillStyle = farbe
    ctx.fillRect(x - w / 2, y_oben, w, h)

    ctx.strokeStyle = "rgba(17, 24, 39, 0.45)"
    ctx.lineWidth = 1.2
    ctx.strokeRect(x - w / 2, y_oben, w, h)

    # Beschriftung
    ctx.fillStyle = "#111827"
    ctx.font = "14px system-ui"
    ctx.textAlign = "center"
    ctx.fillText(block["name"], x, y_oben - 34)
    ctx.fillText(f"m = {zahl_deutsch(masse, 1)}", x, y_oben - 16)

    # Geschwindigkeitspfeil
    pfeil_laenge = begrenze_wert(block["v"] / 250 * 90, -90, 90)
    zeichne_pfeil(x, y_oben - 52, pfeil_laenge, "#111827")


def zeichne_hintergrund():
    breite = sim_canvas.width
    hoehe = sim_canvas.height

    ctx.clearRect(0, 0, breite, hoehe)

    # Himmel / Hintergrund
    ctx.fillStyle = "#f9fafb"
    ctx.fillRect(0, 0, breite, hoehe)

    # Unterlage
    ctx.fillStyle = "#e5e7eb"
    ctx.fillRect(0, GROUND_Y, breite, hoehe - GROUND_Y)

    ctx.strokeStyle = "#6b7280"
    ctx.lineWidth = 2
    ctx.beginPath()
    ctx.moveTo(0, GROUND_Y)
    ctx.lineTo(breite, GROUND_Y)
    ctx.stroke()

    # Skizzenhafte horizontale Linie
    ctx.strokeStyle = "rgba(107, 114, 128, 0.25)"
    ctx.lineWidth = 1
    for x in range(0, breite, 50):
        ctx.beginPath()
        ctx.moveTo(x, GROUND_Y + 28)
        ctx.lineTo(x + 28, GROUND_Y + 28)
        ctx.stroke()


def zeichne_status():
    ctx.textAlign = "left"
    ctx.font = "15px system-ui"
    ctx.fillStyle = "#111827"

    if not laeuft and not stoss_passiert:
        status = "Status: bereit"
    elif laeuft and not stoss_passiert:
        status = "Status: läuft"
    elif stoss_passiert:
        status = "Status: Stoß passiert"
    else:
        status = "Status: —"

    ctx.fillText(status, 16, 26)
    ctx.fillText(f"Stoßzahl e = {zahl_deutsch(e, 2)}", 16, 48)

    if heat_colors_checkbox.checked:
        ctx.fillText("Farbmodus: blau = keine Dissipation, rot = maximale Dissipation", 16, 70)

    if stoss_passiert:
        ctx.fillText(f"Energieverlust ΔE = {zahl_deutsch(e_diss, 2)}", 16, 92)


def draw():
    """
    Zeichnet die komplette Simulation.
    """
    zeichne_hintergrund()

    zeichne_block(block1, m1, "#2563eb")
    zeichne_block(block2, m2, "#16a34a")

    zeichne_status()


# ================================================================
# 6. Interaktion
# ================================================================

@when("input", "#mass-1")
def mass_1_geaendert(event):
    if not laeuft:
        aktualisiere_parameter_und_startzustand()
        draw()


@when("input", "#velocity-1")
def velocity_1_geaendert(event):
    if not laeuft:
        aktualisiere_parameter_und_startzustand()
        draw()


@when("input", "#mass-2")
def mass_2_geaendert(event):
    if not laeuft:
        aktualisiere_parameter_und_startzustand()
        draw()


@when("input", "#velocity-2")
def velocity_2_geaendert(event):
    if not laeuft:
        aktualisiere_parameter_und_startzustand()
        draw()


@when("input", "#restitution")
def restitution_geaendert(event):
    if not laeuft:
        aktualisiere_parameter_und_startzustand()
        draw()


@when("change", "#heat-colors")
def heat_colors_geaendert(event):
    if not laeuft:
        draw()


@when("click", "#start-button")
def start(event):
    global laeuft, letzter_zeitpunkt

    aktualisiere_parameter_und_startzustand()

    laeuft = True
    letzter_zeitpunkt = None

    setze_controls_aktiv(False)


@when("click", "#reset-button")
def reset(event):
    global laeuft, stoss_passiert, letzter_zeitpunkt

    laeuft = False
    stoss_passiert = False
    letzter_zeitpunkt = None

    setze_controls_aktiv(True)
    aktualisiere_parameter_und_startzustand()
    draw()


# ================================================================
# 7. Zeitentwicklung
# ================================================================

def update(dt):
    """
    Berechnet einen Zeitschritt.

    Physikalisch passiert nur:
        freie Bewegung auf reibungsfreier Unterlage
        einmaliger Stoß bei Kontakt
    """
    if not laeuft:
        return

    block1["x"] += block1["v"] * dt
    block2["x"] += block2["v"] * dt

    pruefe_stoss()


def animationsschritt(zeitpunkt):
    global letzter_zeitpunkt

    if letzter_zeitpunkt is None:
        letzter_zeitpunkt = zeitpunkt

    dt = (zeitpunkt - letzter_zeitpunkt) / 1000.0
    letzter_zeitpunkt = zeitpunkt

    dt = min(dt, MAX_DT)

    update(dt)
    draw()
    request()


def request():
    """
    Fordert den nächsten Animationsschritt an.
    """
    window.requestAnimationFrame(animations_proxy)


# ================================================================
# Initialisierung
# ================================================================

aktualisiere_parameter_und_startzustand()
draw()

animations_proxy = create_proxy(animationsschritt)
request()