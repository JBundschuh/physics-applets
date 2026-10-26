# Heat Conduction – Spring–Mass Grid

A standalone JavaScript web applet for qualitatively exploring heat conduction in a solid through a coupled spring–mass lattice. The application uses HTML Canvas and has no external library or runtime dependencies.

## Run

Open `index.html` in a modern browser, or serve the project locally:

```bash
cd heat_conduction_spring-grid
python -m http.server 8000
```

Then visit <http://localhost:8000>. The project can also be hosted as a static site on GitHub Pages.

## Files

- `index.html` – English interface and applet layout
- `style.css` – Layout, colors and responsive styling
- `main.js` – Spring–mass model, numerical integration, energy diagnostics and Canvas rendering

## Model

The applet uses a 10 × 10 grid of movable nodes connected to their neighbors by springs. An initial model temperature determines each node's initial speed and a random initial velocity direction. The **model temperature** is proportional to the node's kinetic energy:

```text
T_model ∝ vx² + vy²
```

Random reorientation of velocities helps break up coherent mechanical waves. Reorientation preserves each node's speed (and thus its kinetic energy), apart from floating-point rounding. Additional invisible, nonlinear restoring springs connect each node to its original grid position to keep the lattice near its rest geometry. Their energy is included in all potential-energy calculations.

The dynamics use the **symplectic Euler method** with a fixed time step. The speed control changes the number of substeps per displayed animation frame rather than increasing the integration step size.

## Energy profile and colors

The lower chart shows **total mechanical energy per grid column**, not temperature or speed:

```text
E_total = E_kinetic + E_potential
```

Potential energy includes both the visible neighbor springs and the invisible restoring springs. Each neighbor spring's potential energy is split equally between its two endpoints; each restoring spring contributes only to its own node. Summing the energies of all ten columns gives the total energy shown in the measurement panel (up to floating-point rounding).

Node color represents **local total mechanical energy** using the same allocation. The fixed color scale goes from blue (low) to orange/red (high); values above the reference energy are capped at the highest color. The reference is the kinetic energy of a node with an initial model temperature of 120. Profile markers use the same color scale for the **mean energy per node in each column**.

Model temperature and temperature difference remain separate diagnostics based on kinetic energy; they are not the quantities shown in the energy profile.

## Controls

- **Start/Pause and Reset:** Play or reinitialize the lattice using the current initial-temperature values.
- **Speed:** Adjust the number of numerical substeps per frame.
- **Grid stiffness / coupling:** Adjust neighbor springs and restoring springs together.
- **Initial temperatures:** Set left, interior and right initial node speeds. If changed while paused, the simulation reinitializes immediately; while running, these are used after Reset, unless boundary-temperature maintenance is active.
- **Maintain boundary temperatures:** Rescale the speeds of the left and right nodes to maintain their target model temperatures. The nodes are not fixed in position, so energy can be exchanged with the rest of the lattice.

The movement of nodes and their connecting springs is always visible.

## Limitations

This is a deliberately simplified, dimensionless mechanical model, **not** a physically exact atomistic simulation of heat conduction. It qualitatively illustrates energy redistribution in a coupled solid. Without boundary temperature control, the model's total mechanical energy should be approximately conserved, subject to numerical error. With boundary heat baths enabled, total energy can change as energy is supplied or removed.
