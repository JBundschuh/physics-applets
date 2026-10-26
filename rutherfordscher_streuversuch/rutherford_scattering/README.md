# Rutherford Scattering

An interactive, dependency-free JavaScript applet for a qualitative visualization of alpha-particle scattering by gold nuclei.

## Views

- **Particle trajectories:** Alpha particles travel through the scaled Coulomb field of several gold nuclei. Particle trails and a qualitative field overlay can be toggled.
- **Scattering statistics:** Simplified Rutherford experiment with a source, collimator, gold foil, detector screen, angle counts, and a linear or logarithmic histogram. Scattering angles are sampled from an impact-parameter model.

Adjustable parameters: alpha-particle energy, nuclear charge, particle rate, animation speed, and model foil thickness (used in the statistics view). The visualization is **not to scale**; its fields, parameters, and probabilities are scaled for educational purposes. Only the Rutherford nuclear model is included.

## Run

Open `index.html` in a browser, or use a local HTTP server:

```bash
python -m http.server 8000
```

Then open `http://localhost:8000`. No Python runtime, PyScript, or external JavaScript libraries are required. You can also deploy these files directly to GitHub Pages.

## Files

- `index.html` — English user interface
- `style.css` — original visual design
- `main.js` — scattering model, canvas rendering, and event handling
