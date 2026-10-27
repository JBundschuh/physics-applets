# Sound Propagation in a Solid

This dependency-free JavaScript applet visualizes longitudinal wave propagation in a solid using a discrete spring–mass model. The apparent 2D lattice has **one dynamical degree of freedom per column**: all nodes in each column represent a material layer with the same horizontal displacement.

## Run

Open `index.html` in a modern browser, or publish the four project files on GitHub Pages. No Python installation, PyScript runtime, dependencies, or build step is required.

## Files

- `index.html` — English user interface and canvas elements
- `main.js` — model equations, animation, wave profiles, and interactions
- `style.css` — original layout and styling
- `README.md` — this documentation

## Model

Each interior material layer obeys

```text
m ü_j = k (u_(j+1) - 2 u_j + u_(j-1)).
```

The equations are integrated with the symplectic Euler method at a fixed timestep. The leftmost layer can be driven by a smooth, finite pulse or a periodic signal. The right boundary is selectable: **free**, **fixed**, or **absorbing** (impedance-matched damping). There is no transverse motion, thermal jitter, diagonal spring coupling, or auxiliary stabilization.

The optional continuum approximation is computed independently using

```text
u(x, t) = g(t - x/c),    c = a sqrt(k/m),
```

plus the **first reflection** at the right boundary (same displacement sign for a free end, inverted for a fixed end; no ideal reflection for an absorbing end). It does not include additional reflections at the source. Long-wavelength lattice motion approaches the continuum result; short waves exhibit discrete-lattice dispersion.

## Energy coloring

The grayscale of each column represents its local mechanical energy: kinetic energy plus one-half of the potential energy of each neighboring spring. Darker means more energy. The color scale adjusts to the displayed energy range, with a reference floor.

The source injects energy when excited. The absorbing boundary dissipates energy. Parameters and numerical values are model quantities and are not calibrated to an experimental solid.
