# Temperaturfeld-Wärmeleitung · Fourier-Modell

Dieses Applet ist eine einfachere Alternative zum Feder-Masse-Gitter.

Die Temperaturwerte werden direkt mit einer diskreten 1D-Wärmeleitungsgleichung berechnet.
Das sichtbare 2D-Gitter dient nur der Darstellung: Die Punkte zittern abhängig von der Temperatur ihrer Spalte.

## Start

Nicht per Doppelklick öffnen, sondern lokal über einen kleinen Server:

```bash
cd temperaturfeld_waermeleitung_fourier
python -m http.server 8000
```

Dann im Browser öffnen:

```text
http://localhost:8000
```

## Modell

- 10 Spalten, 10 Reihen
- ein Temperaturwert pro Spalte
- Wärmeleitung nur in x-Richtung
- optional feste linke/rechte Randtemperatur
- thermische Bewegung ist nur Visualisierung; ihre Stärke ist im Python-Code festgelegt
- Gitterpfade und thermische Bewegung werden dauerhaft angezeigt

## Didaktischer Hinweis

Das Zittern der Punkte ist nicht die physikalische Rechenursache der Wärmeleitung. Es veranschaulicht nur, dass höhere Temperatur mit stärkerer ungeordneter thermischer Bewegung verbunden ist.
