# Temperaturfeld-Wärmeleitung

PyScript-Applet zur qualitativen Darstellung von Wärmeleitung mit einem Feder-Masse-Gitter.

## Start

Nicht per Doppelklick öffnen, sondern mit einem lokalen Server starten:

```bash
cd temperaturfeld_waermeleitung
python -m http.server 8000
```

Dann im Browser öffnen:

```text
http://localhost:8000
```

## Dateien

- `index.html` – HTML-Struktur und PyScript-Einbindung
- `style.css` – Layout und Gestaltung
- `main.py` – Feder-Masse-Modell, Energieauswertung, Animation und Canvas-Zeichnung

## Modellidee

Das Applet nutzt ein 10×10-Gitter aus Knoten. Benachbarte Knoten sind über sichtbare Federn gekoppelt. Die lokale Modelltemperatur ergibt sich aus der kinetischen Energie eines Knotens:

```text
T_modell ~ vx² + vy²
```

Zusätzlich werden Geschwindigkeitsrichtungen zufällig gestreut, ohne den Betrag zu ändern. Dadurch bleibt kinetische Energie erhalten, aber geordnete mechanische Wellen werden in ungeordnetere thermische Bewegung überführt.

## Energieprofil

Das untere Diagramm zeigt die **Gesamtenergie je Gitterspalte** als Summe aus
kinetischer und potenzieller Energie (dimensionslose Modellwerte). Die
potenzielle Energie umfasst sowohl die sichtbaren Nachbarfedern als auch die
unsichtbaren Rückstellfedern zur Gleichgewichtslage.

Die Energie einer Nachbarfeder wird jeweils zur Hälfte den beiden verbundenen
Knoten und damit ihren Spalten zugeordnet. Die Rückstellfederenergie wird
vollständig der Spalte ihres Knotens zugeordnet. Die Summe aller zehn
Spaltenenergien entspricht der angezeigten Gesamtenergie (bis auf Rundung).

Die Knotenfarbe zeigt die **lokale Gesamtenergie** (kinetisch und potenziell).
Die Energie einer Nachbarfeder wird zu gleichen Teilen auf ihre Endknoten
verteilt; die Rückstellfederenergie gehört zum jeweiligen Knoten. Die Farben
reichen von Blau (wenig Energie) bis Orange/Rot (viel Energie). Als feste
Farbreferenz dient die kinetische Energie eines Knotens bei Modelltemperatur
120; darüber liegende Energien werden mit der höchsten Farbstufe dargestellt.
Die Punkte im Energieprofil verwenden dieselbe Farbskala auf Basis der
mittleren Energie pro Knoten in der jeweiligen Spalte.

Die separat angezeigte Modelltemperatur wird weiterhin nur aus der
kinetischen Energie abgeleitet. Das physikalische Modell bleibt unverändert.

## Modellgrenze

Das Applet ist keine exakte Atomsimulation. Jeder Knoten steht modellhaft für einen Gitterplatz bzw. kleinen Bereich eines Festkörpers. Die Simulation soll Wärmeleitung qualitativ verständlich machen.

## Bedienung

Die Knotenbewegung und die Kopplungsfedern sind stets sichtbar. Über Geschwindigkeit und Gittersteifigkeit lässt sich die Simulation steuern. Optional können die beiden Randtemperaturen durch Wärmebäder konstant gehalten werden.
