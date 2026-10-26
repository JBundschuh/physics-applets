# Particle Motion and Speed Distribution

A browser-based, two-dimensional particle simulation with a speed histogram and a theoretical Rayleigh distribution. The application is implemented in plain JavaScript, HTML, and CSS without external dependencies.

## Run

Open `index.html` in a modern browser. You can also host the files on any static web server, including GitHub Pages.

## Controls

- **Temperature T (100–1000 K):** Rescales particle velocities according to the square root of temperature.
- **Number of particles N (20–250):** Reinitializes the particles when changed.
- **Pause / Start:** Stops or resumes time evolution.
- **Reset:** Reinitializes the current number of particles at the selected temperature.

## Model

Particles move in a two-dimensional rectangular container. They have equal model masses and radii. Wall reflections and particle-particle collisions are elastic. For equal particle masses, only the velocity components along the collision normal change during a collision.

Each initial velocity component is sampled from a normal distribution with standard deviation

\[\sigma(T)=85\,\mathrm{px/s}\sqrt{T/(300\,\mathrm{K})}.\]

Consequently, the theoretical speed distribution is the **two-dimensional Rayleigh distribution**:

\[f(v)=\frac{v}{\sigma^2}\exp\left(-\frac{v^2}{2\sigma^2}\right).\]

The histogram shows a normalized speed density. Particle and histogram-bar colors represent speed on a fixed blue–cyan–yellow–red scale. The small measurement box reports the mean particle speed and total kinetic model energy.

## Limitations

This is an illustrative 2D model, not a physically calibrated gas simulation. Pixel-based speeds and dimensionless model mass do not constitute a consistent SI scaling. The temperature slider rescales velocities; it is not an active thermostat during subsequent collisions. The theoretical curve describes the initial Gaussian velocity ensemble rather than enforcing a distribution at every time step. Collision detection uses pairwise overlap checks and a discrete time step.

## Files

- `index.html` — user interface and canvases
- `style.css` — original visual layout with English class names
- `main.js` — numerical model, elastic collisions, rendering, and interaction
