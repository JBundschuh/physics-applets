# Schallausbreitung im Spaltenmodell

Dieses PyScript-Applet zeigt die longitudinale Wellenausbreitung in einem
Festkörper als diskretes Feder-Masse-Modell. Das sichtbare Flächengitter besitzt
nur einen dynamischen Freiheitsgrad je Spalte. Alle Punkte einer Spalte stellen
dieselbe gemeinsam bewegte Materialschicht dar.

## Start

Die Dateien müssen über einen lokalen Webserver bereitgestellt werden, zum
Beispiel im Projektordner mit:

```bash
python3 -m http.server 8000
```

Danach `http://localhost:8000` im Browser öffnen. Beim ersten Start lädt
PyScript seine Laufzeit aus dem Internet.

## Modell

Für innere Materialschichten gilt

```text
m ü_j = k (u_(j+1) - 2 u_j + u_(j-1)).
```

Die Simulation integriert dieses diskrete Gleichungssystem direkt. Es gibt
keine Modellstabilisierung, diagonalen Federn, thermische Bewegung oder
transversalen Freiheitsgrade.

Die optionale Kontinuumskurve verwendet unabhängig davon

```text
u(x,t) = g(t - x/c),   c = a sqrt(k/m),
```

und ist vor der ersten Reflexion am rechten Rand als Vergleich gedacht. Lange
Wellen des Gitters nähern sich dieser Kurve an; kurze Wellen zeigen die
Dispersion des diskreten Modells.

## Energieanzeige

Die Graustufe jeder Spalte zeigt ihre lokale mechanische Gesamtenergie:
kinetische Energie plus jeweils die Hälfte der Energie der angrenzenden Federn.

Beim absorbierenden Rand wird Energie gezielt durch einen angepassten Dämpfer
aus dem dargestellten System abgeführt. Beim Signalgenerator und während des
Pulses führt die Quelle Energie zu.
