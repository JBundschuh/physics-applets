# Rutherford-Streuung

Interaktives PyScript-Applet zur qualitativen Darstellung der Rutherford-Streuung von Alphateilchen an Goldkernen.

## Ansichten

- **Bahnansicht:** Alphateilchen bewegen sich durch das didaktisch skalierte Coulombfeld mehrerer Goldkerne. Bahnspuren und die qualitative Felddarstellung sind zuschaltbar.
- **Streuwinkelstatistik:** Vereinfachter Rutherford-Versuch mit Quelle, Kollimator, Goldfolie, Zählschirm, Zählwerten und linearem oder logarithmischem Winkelhistogramm. Die Winkel werden mit einem Stoßparametermodell erzeugt.

Einstellbar sind Alphaenergie, Kernladung, Teilchenrate, Simulationsgeschwindigkeit und eine modellierte Foliendicke. Das Applet ist nicht maßstäblich; die Parameter und Wahrscheinlichkeiten sind didaktisch skaliert.

## Start

Die Dateien `index.html`, `style.css` und `main.py` in einem Ordner speichern und über einen lokalen Webserver öffnen:

```bash
python -m http.server 8000
```

Im Browser `http://localhost:8000` aufrufen. Die PyScript-Laufzeit wird über die in `index.html` eingebundene externe Quelle geladen. Weitere Python-Pakete sind nicht erforderlich.
