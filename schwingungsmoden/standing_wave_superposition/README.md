# Standing Wave Superposition

An interactive, browser-based visualization of standing-wave modes and their superposition in one and two dimensions. Written in plain JavaScript with HTML Canvas and CSS. No framework, Python runtime, build step, or external libraries are required.

## Features

- **1D string with fixed endpoints:** 4–80 string elements, up to five modes, and a signed amplitude slider for each displayed mode.
- **2D planar lattice with fixed boundaries:** 1–5 movable interior masses per direction, a clickable mode matrix, and displacements along x, y, or both axes.
- Play/pause, reset phase, playback speed, phase slider, optional mode overlays, and a toggle between physical frequency ratios and equal mode frequencies.
- Mode selections and amplitude settings are retained when the number of visible modes is reduced and increased again.

## Running the applet

Open `index.html` in a modern browser, or serve the folder as a static site, for example:

```bash
python -m http.server 8000
```

Open `http://localhost:8000` in your browser. For GitHub Pages, publish `index.html`, `main.js`, and `style.css` together in the same folder.

## Model

The 1D string displacement is evaluated directly from the selected standing-wave modes:

\[
y(x,t) = \sum_{n=1}^{N} A_n \sin\left(\frac{n\pi x}{L}\right)\cos(\omega_n t).
\]

For physical frequency ratios, \(\omega_n=n\omega_1\). Otherwise, all modes use \(\omega_1\).

In 2D, each mode uses the spatial shape

\[
\sin\left(\frac{m\pi x}{L_x}\right) \sin\left(\frac{n\pi y}{L_y}\right).
\]

A selected global direction maps this scalar mode shape into displacements within the x-y plane. The illustrative frequency factor is \(\sqrt{m^2+n^2}/\sqrt{2}\) for the physical-ratio option; otherwise all modes use the same frequency. The boundary points remain fixed by construction. The visualization sums prescribed mode shapes rather than numerically integrating a coupled mechanical system.

## Files

- `index.html` — English user interface and canvas.
- `main.js` — standing-wave functions, mode controls, animation, and drawing.
- `style.css` — layout and presentation.

## Scope

This is a simplified educational visualization of normal-mode superposition, not a numerically simulated string or elastic solid. The 2D mode frequencies are a qualitative approximation, not a validated dispersion relation for a specific physical lattice.
