# main.py
# ================================================================
# Physik-Applet mit PyScript
# Thema: Teilchenbewegung und Geschwindigkeitsverteilung
# ================================================================
# Struktur dieses Codes:
# 1. DOM-Zugriff und Zeichenflächen
# 1.1Annahmen
# 2. Parameter
# 3. Modellzustand
# 4. Modellfunktionen
# 5. Zeitentwicklung
# 6. Darstellung
# 7. Interaktion
# 8. Animationsschleife
# ================================================================

from pyscript import document, window, when
from pyscript.ffi import create_proxy
import math
import random


# ================================================================
# 1. DOM-Zugriff und Zeichenflächen
# ================================================================
# Hier holen wir HTML-Elemente aus der Webseite.
# Canvas-Elemente sind Zeichenflächen. Darauf zeichnen wir mit ctx.

sim_canvas = document.getElementById("sim-canvas")
sim_ctx = sim_canvas.getContext("2d")

hist_canvas = document.getElementById("hist-canvas")
hist_ctx = hist_canvas.getContext("2d")

temperature_slider = document.getElementById("temperature")
temperature_value = document.getElementById("temperature-value")

particle_count_slider = document.getElementById("particle-count")
particle_count_value = document.getElementById("particle-count-value")

toggle_button = document.getElementById("toggle-button")

# hier DEBUGG
print("PyScript läuft")
print("sim_canvas:", sim_canvas)
print("hist_canvas:", hist_canvas)

# ================================================================
# 1.1. Annahmen
# ================================================================
# Alle Teilchen haben gleiche Masse
# Alle Teilchen haben gleichen Radius
# Stöße sind elastisch
# Keine Reibung
# Keine Energieverluste
# Keine echte SI-Skalierung
# 2D-Modell bleibt erhalten


# ================================================================
# 2. Parameter
# ================================================================
# Diese Werte beschreiben das Modell und die Darstellung.
# Die Temperatur ist hier ein Modellparameter. Sie steuert die typische
# Geschwindigkeit der Teilchen über v ~ sqrt(T).

BASIS_TEMPERATUR = 300.0          # Referenztemperatur in K
BASIS_SIGMA = 85.0                # typische Komponenten-Geschwindigkeit bei 300 K in px/s
TEILCHEN_RADIUS = 4.0             # Radius eines Teilchens in Pixeln
MAX_DT = 0.04                     # maximale Zeitschrittweite in Sekunden
TEILCHEN_MASSE = 1.0              # Modellmasse; keine echte SI-Einheit

# Parameter für Teilchen-Teilchen-Stöße
KOLLISIONEN_AKTIV = True
STOSS_ITERATIONEN = 1             # 1 reicht für den Anfang; bei vielen Teilchen ggf. 2
MIN_ABSTAND = 2.0 * TEILCHEN_RADIUS

T = float(temperature_slider.value)
N = int(particle_count_slider.value)

laeuft = True                     # True: Simulation läuft, False: pausiert
letzter_zeitpunkt = None          # wird in der Animationsschleife gesetzt

# Farbskala für die Teilchengeschwindigkeit
# Die Farbskala ist absolut gewählt:
# Bei höherer Temperatur werden im Mittel mehr Teilchen gelb/rot.
TEMPERATUR_MAX_FUER_FARBE = 1000.0
FARB_GESCHWINDIGKEIT_MAX_FAKTOR = 3.0


# ================================================================
# 3. Modellzustand
# ================================================================
# Jedes Teilchen wird als Dictionary gespeichert:
# x, y   : Position
# vx, vy : Geschwindigkeit in x- und y-Richtung

teilchen = []


# ================================================================
# 4. Modellfunktionen
# ================================================================

def sigma_aus_temperatur(temperatur):
    """
    Berechnet die Standardabweichung der Geschwindigkeitskomponenten.

    Modellidee:
    Bei einem idealisierten Gas gilt qualitativ:
        typische Geschwindigkeit ~ sqrt(T)

    Hier benutzen wir keine SI-Einheiten, sondern Pixel pro Sekunde,
    weil wir eine Bildschirmvisualisierung erzeugen.
    """
    return BASIS_SIGMA * math.sqrt(temperatur / BASIS_TEMPERATUR)


def neue_geschwindigkeit(temperatur):
    """
    Erzeugt eine zufällige Anfangsgeschwindigkeit.

    Die Komponenten vx und vy werden normalverteilt gewählt.
    Dadurch entsteht in 2D eine Rayleigh-artige Verteilung der
    Geschwindigkeitsbeträge.
    """
    sigma = sigma_aus_temperatur(temperatur)
    vx = random.gauss(0.0, sigma)
    vy = random.gauss(0.0, sigma)
    return vx, vy


def initialisiere_teilchen():
    """
    Erstellt alle Teilchen neu.

    Diese Funktion wird beim Start, beim Reset und bei Änderung der
    Teilchenzahl verwendet.
    """
    global teilchen

    teilchen = []

    breite = sim_canvas.width
    hoehe = sim_canvas.height

    for _ in range(N):
        vx, vy = neue_geschwindigkeit(T)

        teilchen.append({
            "x": random.uniform(TEILCHEN_RADIUS, breite - TEILCHEN_RADIUS),
            "y": random.uniform(TEILCHEN_RADIUS, hoehe - TEILCHEN_RADIUS),
            "vx": vx,
            "vy": vy,
        })


def skaliere_geschwindigkeiten(alte_temperatur, neue_temperatur):
    """
    Passt vorhandene Geschwindigkeiten an eine neue Temperatur an.

    Weil v ~ sqrt(T) gilt, werden alle Geschwindigkeiten mit
    sqrt(T_neu / T_alt) multipliziert.
    """
    if alte_temperatur <= 0:
        return

    faktor = math.sqrt(neue_temperatur / alte_temperatur)

    for p in teilchen:
        p["vx"] *= faktor
        p["vy"] *= faktor


def geschwindigkeitsbetraege():
    """
    Gibt eine Liste aller Geschwindigkeitsbeträge zurück.
    """
    werte = []

    for p in teilchen:
        v = math.sqrt(p["vx"] ** 2 + p["vy"] ** 2)
        werte.append(v)

    return werte

def mittlere_geschwindigkeit():
    """
    Berechnet die mittlere Geschwindigkeit aller Teilchen.

    Gemeint ist der Mittelwert der Geschwindigkeitsbeträge:
        <v> = (v1 + v2 + ... + vN) / N

    Die Einheit ist hier px/s, weil die Simulation in Pixeln arbeitet.
    """
    werte = geschwindigkeitsbetraege()

    if len(werte) == 0:
        return 0.0

    return sum(werte) / len(werte)


def gesamte_kinetische_energie():
    """
    Berechnet die gesamte kinetische Energie aller Teilchen.

    Modell:
        E_kin = Summe(1/2 * m * v^2)

    Da wir keine echten SI-Einheiten verwenden, ist das eine Modellenergie.
    Für Vergleiche ist sie trotzdem sehr nützlich:

        - Bei elastischen Stößen sollte sie ungefähr konstant bleiben.
        - Beim Temperatur-Slider ändert sie sich gezielt.
    """
    energie = 0.0

    for p in teilchen:
        v_quadrat = p["vx"] ** 2 + p["vy"] ** 2
        energie += 0.5 * TEILCHEN_MASSE * v_quadrat

    return energie


def theoretische_2d_verteilung(v, temperatur):
    """
    Theoretische 2D-Geschwindigkeitsverteilung für dieses Modell.

    Wenn vx und vy normalverteilt sind, ist der Betrag v Rayleigh-verteilt:
        f(v) = v / sigma^2 * exp(-v^2 / (2 sigma^2))

    Das ist die 2D-Variante der Idee hinter Maxwell-Boltzmann.
    """
    sigma = sigma_aus_temperatur(temperatur)
    if sigma <= 0:
        return 0.0

    return (v / sigma ** 2) * math.exp(-v ** 2 / (2 * sigma ** 2))


# ================================================================
# 5. Zeitentwicklung
# ================================================================

def behandle_elastischen_stoss(p1, p2):
    """
    Behandelt den elastischen Stoß zweier gleich schwerer Teilchen.

    Modellannahmen:
        - gleiche Masse
        - gleicher Radius
        - vollkommen elastischer Stoß
        - keine Reibung
        - keine Energieverluste

    Physikalische Idee:
        Nur der Geschwindigkeitsanteil entlang der Verbindungslinie
        der Teilchenmittelpunkte wird verändert.
    """

    # Abstandsvektor von Teilchen 1 zu Teilchen 2
    dx = p2["x"] - p1["x"]
    dy = p2["y"] - p1["y"]

    abstand_quadrat = dx * dx + dy * dy

    # Sonderfall: Teilchen liegen exakt aufeinander.
    # Dann wählen wir eine zufällige Richtung, damit keine Division durch 0 entsteht.
    if abstand_quadrat == 0:
        winkel = random.uniform(0.0, 2.0 * math.pi)
        nx = math.cos(winkel)
        ny = math.sin(winkel)
        abstand = 0.0
    else:
        abstand = math.sqrt(abstand_quadrat)
        nx = dx / abstand
        ny = dy / abstand

    # Prüfen, ob sich die Teilchen überlappen
    ueberlappung = MIN_ABSTAND - abstand

    if ueberlappung <= 0:
        return

    # 1. Positionskorrektur
    # Durch die diskrete Zeitrechnung können Teilchen bereits etwas
    # ineinander stecken. Wir schieben sie entlang der Stoßnormalen
    # auseinander. Beide Teilchen werden gleich stark verschoben.
    korrektur = 0.5 * ueberlappung

    p1["x"] -= korrektur * nx
    p1["y"] -= korrektur * ny
    p2["x"] += korrektur * nx
    p2["y"] += korrektur * ny

    # 2. Geschwindigkeitskorrektur
    # Relativgeschwindigkeit:
    # Wir betrachten, ob sich die Teilchen entlang der Normalen
    # aufeinander zubewegen.
    dvx = p1["vx"] - p2["vx"]
    dvy = p1["vy"] - p2["vy"]

    relativgeschwindigkeit_normal = dvx * nx + dvy * ny

    # Wenn der Wert <= 0 ist, entfernen sich die Teilchen bereits.
    # Dann korrigieren wir nur die Position, aber nicht nochmal die Geschwindigkeit.
    if relativgeschwindigkeit_normal <= 0:
        return

    # Für gleiche Massen und elastischen Stoß:
    # Normalanteil der relativen Geschwindigkeit wird ausgetauscht.
    impuls = relativgeschwindigkeit_normal

    p1["vx"] -= impuls * nx
    p1["vy"] -= impuls * ny

    p2["vx"] += impuls * nx
    p2["vy"] += impuls * ny


def behandle_teilchenstoesse():
    """
    Prüft alle Teilchenpaare auf Kollisionen und behandelt elastische Stöße.

    Einfache Variante:
        Jedes Teilchenpaar wird einmal geprüft.

    Aufwand:
        ungefähr N² / 2 Prüfungen pro Frame.
    Für kleine bis mittlere Teilchenzahlen ist das ausreichend.
    """

    if not KOLLISIONEN_AKTIV:
        return

    anzahl = len(teilchen)

    for _ in range(STOSS_ITERATIONEN):
        for i in range(anzahl):
            for j in range(i + 1, anzahl):
                behandle_elastischen_stoss(teilchen[i], teilchen[j])

def aktualisiere_modell(dt):
    """
    Berechnet einen Zeitschritt der Simulation.

    Ablauf:
        1. Positionen aktualisieren
        2. Wandstöße behandeln
        3. Teilchen-Teilchen-Stöße behandeln

    Die Teilchen-Teilchen-Stöße sind elastisch:
        Gesamtimpuls und Gesamtenergie bleiben erhalten.
    """
    breite = sim_canvas.width
    hoehe = sim_canvas.height

    # 1. Freie Bewegung und Wandstöße
    for p in teilchen:
        p["x"] += p["vx"] * dt
        p["y"] += p["vy"] * dt

        # Reflexion an linker Wand
        if p["x"] < TEILCHEN_RADIUS:
            p["x"] = TEILCHEN_RADIUS
            p["vx"] *= -1

        # Reflexion an rechter Wand
        elif p["x"] > breite - TEILCHEN_RADIUS:
            p["x"] = breite - TEILCHEN_RADIUS
            p["vx"] *= -1

        # Reflexion an oberer Wand
        if p["y"] < TEILCHEN_RADIUS:
            p["y"] = TEILCHEN_RADIUS
            p["vy"] *= -1

        # Reflexion an unterer Wand
        elif p["y"] > hoehe - TEILCHEN_RADIUS:
            p["y"] = hoehe - TEILCHEN_RADIUS
            p["vy"] *= -1

    # 2. Teilchen-Teilchen-Stöße
    behandle_teilchenstoesse()

# ================================================================
# 6. Darstellung
# ================================================================

def zeichne_simulation():
    """
    Zeichnet den Kasten und alle Teilchen.

    Neue Darstellung:
    Die Teilchenfarbe hängt vom Geschwindigkeitsbetrag ab.

        blau  -> langsam
        gelb  -> mittel
        rot   -> schnell
    """
    breite = sim_canvas.width
    hoehe = sim_canvas.height

    # Hintergrund löschen
    sim_ctx.clearRect(0, 0, breite, hoehe)

    # Kastenhintergrund
    sim_ctx.fillStyle = "#f9fafb"
    sim_ctx.fillRect(0, 0, breite, hoehe)

    # Teilchen zeichnen
    for p in teilchen:
        # Geschwindigkeitsbetrag berechnen
        v = math.sqrt(p["vx"] ** 2 + p["vy"] ** 2)

        # Farbe aus Geschwindigkeit bestimmen
        sim_ctx.fillStyle = farbe_aus_geschwindigkeit(v)

        sim_ctx.beginPath()
        sim_ctx.arc(p["x"], p["y"], TEILCHEN_RADIUS, 0, 2 * math.pi)
        sim_ctx.fill()

        # Optional: dünner Rand, damit helle Teilchen sichtbar bleiben
        sim_ctx.strokeStyle = "rgba(17, 24, 39, 0.25)"
        sim_ctx.lineWidth = 0.8
        sim_ctx.stroke()

    # Infotext oben links
    sim_ctx.fillStyle = "#111827"
    sim_ctx.font = "15px system-ui"
    sim_ctx.fillText(f"T = {int(T)} K, N = {N}", 14, 24)

    # # Farblegende oben rechts
    # zeichne_farblegende()

def begrenze_wert(x, minimum, maximum):
    """
    Begrenzt einen Wert auf ein Intervall.

    Beispiel:
        x < minimum  -> minimum
        x > maximum  -> maximum
    """
    return max(minimum, min(maximum, x))


def mische_farben(farbe_a, farbe_b, anteil):
    """
    Mischt zwei RGB-Farben linear.

    farbe_a und farbe_b sind Tupel der Form:
        (rot, gruen, blau)

    anteil = 0 ergibt farbe_a
    anteil = 1 ergibt farbe_b
    """
    anteil = begrenze_wert(anteil, 0.0, 1.0)

    r = int(farbe_a[0] + anteil * (farbe_b[0] - farbe_a[0]))
    g = int(farbe_a[1] + anteil * (farbe_b[1] - farbe_a[1]))
    b = int(farbe_a[2] + anteil * (farbe_b[2] - farbe_a[2]))

    return f"rgb({r}, {g}, {b})"


def farbe_aus_geschwindigkeit(v):
    """
    Ordnet einer Geschwindigkeit eine Farbe zu.

    Farbkarte:
        langsam  -> blau
        mittel   -> türkis / gelb
        schnell  -> rot

    Die Einordnung erfolgt über eine maximale Referenzgeschwindigkeit.
    Diese wird aus der maximalen Temperatur des Sliders abgeschätzt.
    Dadurch sieht man beim Erhöhen der Temperatur auch farblich,
    dass mehr Teilchen schnell werden.
    """
    sigma_max = sigma_aus_temperatur(TEMPERATUR_MAX_FUER_FARBE)
    v_max = FARB_GESCHWINDIGKEIT_MAX_FAKTOR * sigma_max

    if v_max <= 0:
        return "rgb(37, 99, 235)"

    s = begrenze_wert(v / v_max, 0.0, 1.0)

    # Farb-Stützpunkte
    blau = (37, 99, 235)
    tuerkis = (34, 211, 238)
    gelb = (250, 204, 21)
    rot = (220, 38, 38)

    if s < 1.0 / 3.0:
        # blau -> türkis
        lokaler_anteil = s / (1.0 / 3.0)
        return mische_farben(blau, tuerkis, lokaler_anteil)

    elif s < 2.0 / 3.0:
        # türkis -> gelb
        lokaler_anteil = (s - 1.0 / 3.0) / (1.0 / 3.0)
        return mische_farben(tuerkis, gelb, lokaler_anteil)

    else:
        # gelb -> rot
        lokaler_anteil = (s - 2.0 / 3.0) / (1.0 / 3.0)
        return mische_farben(gelb, rot, lokaler_anteil)


# def zeichne_farblegende():
#     """
#     Zeichnet eine kleine Farblegende in die Simulation.

#     Sie zeigt, welche Farben langsame und schnelle Teilchen bedeuten.
#     """
#     x = sim_canvas.width - 180
#     y = 18
#     breite = 130
#     hoehe = 12

#     gradient = sim_ctx.createLinearGradient(x, y, x + breite, y)
#     gradient.addColorStop(0.0, farbe_aus_geschwindigkeit(0.0))
#     gradient.addColorStop(0.33, farbe_aus_geschwindigkeit(0.33 * FARB_GESCHWINDIGKEIT_MAX_FAKTOR * sigma_aus_temperatur(TEMPERATUR_MAX_FUER_FARBE)))
#     gradient.addColorStop(0.66, farbe_aus_geschwindigkeit(0.66 * FARB_GESCHWINDIGKEIT_MAX_FAKTOR * sigma_aus_temperatur(TEMPERATUR_MAX_FUER_FARBE)))
#     gradient.addColorStop(1.0, farbe_aus_geschwindigkeit(FARB_GESCHWINDIGKEIT_MAX_FAKTOR * sigma_aus_temperatur(TEMPERATUR_MAX_FUER_FARBE)))

#     sim_ctx.fillStyle = gradient
#     sim_ctx.fillRect(x, y, breite, hoehe)

#     sim_ctx.strokeStyle = "#374151"
#     sim_ctx.lineWidth = 1
#     sim_ctx.strokeRect(x, y, breite, hoehe)

#     sim_ctx.fillStyle = "#111827"
#     sim_ctx.font = "12px system-ui"
#     sim_ctx.fillText("langsam", x, y + 28)
#     sim_ctx.fillText("schnell", x + breite - 45, y + 28)

def zeichne_messwerte_im_histogramm(links, oben, plot_breite):
    """
    Zeichnet eine kleine Messwert-Box in das Histogramm.

    Angezeigt werden:
        - mittlere Geschwindigkeit <v>
        - gesamte kinetische Energie E_kin

    Diese Werte helfen bei der physikalischen Validierung:
        Bei elastischen Stößen sollte E_kin ohne Temperaturänderung
        ungefähr konstant bleiben.
    """
    v_mittel = mittlere_geschwindigkeit()
    e_kin = gesamte_kinetische_energie()

    box_breite = 190
    box_hoehe = 54

    x = links + plot_breite - box_breite - 8
    y = oben + 8

    # Hintergrund der Box
    hist_ctx.fillStyle = "rgba(255, 255, 255, 0.88)"
    hist_ctx.fillRect(x, y, box_breite, box_hoehe)

    # Rahmen
    hist_ctx.strokeStyle = "rgba(55, 65, 81, 0.35)"
    hist_ctx.lineWidth = 1.0
    hist_ctx.strokeRect(x, y, box_breite, box_hoehe)

    # Text
    hist_ctx.fillStyle = "#111827"
    hist_ctx.font = "13px system-ui"
    hist_ctx.fillText(f"<v> = {v_mittel:.1f} px/s", x + 10, y + 22)
    hist_ctx.fillText(f"E_kin = {e_kin:.0f}", x + 10, y + 42)


def zeichne_histogramm():
    """
    Zeichnet Histogramm der simulierten Geschwindigkeiten und
    theoretische 2D-Verteilungskurve.
    """
    breite = hist_canvas.width
    hoehe = hist_canvas.height

    hist_ctx.clearRect(0, 0, breite, hoehe)
    hist_ctx.fillStyle = "#ffffff"
    hist_ctx.fillRect(0, 0, breite, hoehe)

    # Plotbereich mit Rand
    links = 60
    rechts = 20
    oben = 25
    unten = 45

    plot_breite = breite - links - rechts
    plot_hoehe = hoehe - oben - unten

    werte = geschwindigkeitsbetraege()
    if len(werte) == 0:
        return

    sigma = sigma_aus_temperatur(T)
    max_v = max(max(werte), 4.5 * sigma)
    anzahl_bins = 22
    bin_breite = max_v / anzahl_bins

    # Histogramm zählen
    bins = [0 for _ in range(anzahl_bins)]
    for v in werte:
        index = int(v / bin_breite)
        if index >= anzahl_bins:
            index = anzahl_bins - 1
        bins[index] += 1

    # Dichte statt absoluter Häufigkeit, damit Vergleich mit Kurve sinnvoll ist
    dichten = [count / (len(werte) * bin_breite) for count in bins]

    # Theoriekurve abtasten
    kurve = []
    for i in range(180):
        v = max_v * i / 179
        y = theoretische_2d_verteilung(v, T)
        kurve.append((v, y))

    max_y = max(max(dichten), max(y for _, y in kurve))
    if max_y <= 0:
        max_y = 1.0

    def x_canvas(v):
        return links + (v / max_v) * plot_breite

    def y_canvas(y):
        return oben + plot_hoehe - (y / max_y) * plot_hoehe

    # Achsen
    hist_ctx.strokeStyle = "#374151"
    hist_ctx.lineWidth = 1.0
    hist_ctx.beginPath()
    hist_ctx.moveTo(links, oben)
    hist_ctx.lineTo(links, oben + plot_hoehe)
    hist_ctx.lineTo(links + plot_breite, oben + plot_hoehe)
    hist_ctx.stroke()

    # Histogrammbalken
    # Die Farbe jedes Balkens wird aus der mittleren Geschwindigkeit
    # des jeweiligen Geschwindigkeitsintervalls bestimmt.
    for i, dichte in enumerate(dichten):
        v_links = i * bin_breite
        v_rechts = (i + 1) * bin_breite
        v_mitte = 0.5 * (v_links + v_rechts)
    
        x0 = x_canvas(v_links)
        x1 = x_canvas(v_rechts)
        y = y_canvas(dichte)
    
        balken_breite = max(1, x1 - x0 - 2)
        balken_hoehe = oben + plot_hoehe - y
    
        # Farbe passend zur Geschwindigkeit wählen
        hist_ctx.fillStyle = farbe_aus_geschwindigkeit(v_mitte)
        hist_ctx.fillRect(x0 + 1, y, balken_breite, balken_hoehe)
    
        # Dünner Rand für bessere Sichtbarkeit
        hist_ctx.strokeStyle = "rgba(17, 24, 39, 0.18)"
        hist_ctx.lineWidth = 0.6
        hist_ctx.strokeRect(x0 + 1, y, balken_breite, balken_hoehe)

    # Theoriekurve
    hist_ctx.strokeStyle = "#dc2626"
    hist_ctx.lineWidth = 2.5
    hist_ctx.beginPath()
    for i, (v, y) in enumerate(kurve):
        x = x_canvas(v)
        yy = y_canvas(y)
        if i == 0:
            hist_ctx.moveTo(x, yy)
        else:
            hist_ctx.lineTo(x, yy)
    hist_ctx.stroke()

    # Beschriftung
    hist_ctx.fillStyle = "#111827"
    hist_ctx.font = "14px system-ui"
    hist_ctx.fillText("Geschwindigkeit v / px s⁻¹", links + plot_breite / 2 - 90, hoehe - 12)
    hist_ctx.fillText("Dichte", 10, oben + 12)

    hist_ctx.font = "13px system-ui"
    hist_ctx.fillStyle = "#111827"
    hist_ctx.fillText("Histogramm (Farbe = Geschwindigkeit)", links + 12, oben + 18)
    
    hist_ctx.fillStyle = "#dc2626"
    hist_ctx.fillText("Theorie", links + 250, oben + 18)

    # x-Achsen-Werte
    hist_ctx.fillStyle = "#374151"
    hist_ctx.fillText("0", links - 4, oben + plot_hoehe + 20)
    hist_ctx.fillText(f"{int(max_v)}", links + plot_breite - 25, oben + plot_hoehe + 20)

    # Messwerte anzeigen
    zeichne_messwerte_im_histogramm(links, oben, plot_breite)

def zeichne_alles():
    """
    Zeichnet beide Darstellungen.
    """
    zeichne_simulation()
    zeichne_histogramm()


# ================================================================
# 7. Interaktion
# ================================================================

@when("input", "#temperature")
def temperatur_geaendert(event):
    """
    Wird aufgerufen, wenn der Temperatur-Slider bewegt wird.
    """
    global T

    alte_temperatur = T
    T = float(temperature_slider.value)

    skaliere_geschwindigkeiten(alte_temperatur, T)
    temperature_value.textContent = str(int(T))

    zeichne_alles()


@when("input", "#particle-count")
def teilchenzahl_geaendert(event):
    """
    Wird aufgerufen, wenn die Teilchenzahl verändert wird.
    Für Einfachheit initialisieren wir alle Teilchen neu.
    """
    global N

    N = int(particle_count_slider.value)
    particle_count_value.textContent = str(N)

    initialisiere_teilchen()
    zeichne_alles()


@when("click", "#toggle-button")
def start_pause(event):
    """
    Startet oder pausiert die Simulation.
    """
    global laeuft

    laeuft = not laeuft
    toggle_button.textContent = "Pause" if laeuft else "Start"


@when("click", "#reset-button")
def reset(event):
    """
    Setzt das Modell neu auf.
    """
    initialisiere_teilchen()
    zeichne_alles()


# ================================================================
# 8. Animationsschleife
# ================================================================

def animationsschritt(zeitpunkt):
    """
    Diese Funktion wird vom Browser ungefähr einmal pro Bildschirmbild
    aufgerufen. Sie ist das Herz der Animation.

    Ablauf:
        1. vergangene Zeit dt berechnen
        2. Modell aktualisieren
        3. Darstellung neu zeichnen
        4. nächsten Animationsschritt anfordern
    """
    global letzter_zeitpunkt

    if letzter_zeitpunkt is None:
        letzter_zeitpunkt = zeitpunkt

    dt = (zeitpunkt - letzter_zeitpunkt) / 1000.0
    letzter_zeitpunkt = zeitpunkt

    # Falls der Browser kurz hängt, begrenzen wir dt.
    # Sonst könnten Teilchen bei einem großen Zeitschritt durch Wände springen.
    dt = min(dt, MAX_DT)

    if laeuft:
        aktualisiere_modell(dt)

    zeichne_alles()

    window.requestAnimationFrame(animations_proxy)


# Initialisierung
initialisiere_teilchen()
zeichne_alles()

# Python-Funktion als JavaScript-Callback nutzbar machen.
animations_proxy = create_proxy(animationsschritt)
window.requestAnimationFrame(animations_proxy)
