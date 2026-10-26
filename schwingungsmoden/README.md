# Überlagerung stehender Wellen

Ein einfaches PyScript-Applet zur Demonstration der Überlagerung stehender Wellen.

## Dateien

- `index.html` – HTML-Struktur und PyScript-Einbindung
- `style.css` – Gestaltung der Oberfläche
- `main.py` – Modelllogik, UI-Events und Canvas-Zeichnung

## Inhalt

- 1D-Saite mit festen Enden
- 1D-Amplituden-Slider für die ersten fünf Eigenmoden
- 2D-Gitterschwingung mit festen Rändern und In-Plane-Auslenkung
- 2D-Modenmatrix: Kästchen schalten Moden ein oder aus
- Play/Pause, Reset, Geschwindigkeit, Phase/Zeit

## Starten

Da PyScript externe Python-Dateien über den Browser lädt, sollte das Applet über einen lokalen Webserver gestartet werden:

```bash
python -m http.server 8000
```

Danach im Browser öffnen:

```text
http://localhost:8000
```

## Hinweis

Das Applet verwendet keine externen Python-Pakete wie NumPy. Die Schwingungen werden direkt mit `math.sin` und `math.cos` berechnet.
