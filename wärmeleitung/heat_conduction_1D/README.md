# Heat Conduction in a Temperature Field

An interactive, browser-based visualization of a simplified one-dimensional heat conduction model. Implemented with **vanilla JavaScript**, HTML Canvas, and CSS, without external libraries or a Python runtime.

## Run locally

Open `index.html` in a current browser. No build step or local web server is required. Alternatively, serve this directory with any static web server:

```bash
python -m http.server 8000
```

Then visit `http://localhost:8000`.

To publish with GitHub Pages, place `index.html`, `main.js`, and `style.css` in the same directory and enable Pages for that branch and folder.

## Model

- The grid contains 10 columns and 10 rows, with **one calculated temperature per column**.
- Heat is exchanged between adjacent columns along the horizontal direction; all updates use the previous temperature state.
- The exchange factor `a` is a dimensionless model parameter, not a material's thermal conductivity.
- By default, the boundaries are not fixed. The sum of the column temperatures is then conserved apart from floating-point rounding.
- Optionally, the left and right boundary temperatures can be held at their selected values.
- The grid lines are always shown. Node motion is a temperature-dependent visualization only; its fixed strength is set by `JITTER_STRENGTH` in `main.js`.
- **Speed** changes the number of numerical updates per animation frame (as in the original version), not physical elapsed time.

### Discrete update rule

For interior columns, the implemented pairwise exchange is equivalent to

`T_new[i] = T[i] + a * (T[i - 1] - 2 * T[i] + T[i + 1])`.

At free outer boundaries there is only one neighboring column. When fixed boundaries are enabled, the outer values are restored after each numerical step.

The displayed **sum of temperatures** is simply the sum of the ten column values. It is not a calculation of thermodynamic heat or energy. Temperature values have no explicitly assigned physical unit in this simplified model.

## Educational note

The moving nodes do **not** determine the heat exchange. Their motion only illustrates the idea that higher temperature can be associated with stronger microscopic thermal agitation. This is not a mechanical particle simulation.
