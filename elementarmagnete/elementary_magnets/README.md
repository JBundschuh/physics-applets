# Elementary Magnets – Weiss Domains and Magnetization

A standalone interactive educational web applet showing magnetic moments in a two-dimensional sample. Written entirely in **HTML, CSS, and JavaScript**; no PyScript, Python, NumPy, build step, or other external dependencies are required.

## Run

Open `index.html` directly in a modern web browser, or upload `index.html`, `main.js`, and `style.css` together to a static web host such as GitHub Pages.

## Controls and experiments

- **Material:** soft ferromagnet, hard ferromagnet, or an idealized paramagnet.
- **Initial state:** multiple domains or magnetized (not applicable to the paramagnet).
- **Enable magnet:** show and activate the external bar magnet; drag it with the mouse or a touchscreen to vary the applied field. Use **Reverse poles** to rotate its polarity by 180°.
- **Temperature:** vary the strength of the stochastic angular fluctuations.
- **Show external magnetic field:** toggle arrows representing the external bar magnet's field only, not the complete internal + external field.
- **Pause / Start / Reset:** control the evolution and restore the selected sample's starting state.

**Pole colors:** north is **red**, south is **blue**, both for the external bar magnet and the individual magnetic-moment symbols.

## Physical model

The displayed 24 × 16 grid consists of unit magnetic moments confined to the sample plane. Each arrow represents a *local magnetic moment*, not an entire Weiss domain. The classical effective energy consists of exchange, easy-axis anisotropy, dipole-dipole interactions, and interaction with the external field:

```
E = -J Σ_<i,j> s_i · s_j
    - Σ_i K_i (s_i · e_x)²
    - ½ Σ_i s_i · B_dip,i
    - Σ_i s_i · B_ext,i
```

The dipolar interaction uses the usual 1/r³ spatial decay evaluated on a planar grid, without self-interaction. The bar magnet is represented by seven equally oriented dipole sources with finite soft-core radius to avoid singularities during dragging. The same spatially fixed pinning profile is used for the material presets, with different strengths. The idealized paramagnetic preset has no exchange, anisotropy, or internal dipole interaction.

The angle of each moment evolves according to **overdamped Euler–Maruyama relaxation** with Gaussian noise:

```
dθ_i = -∂E/∂θ_i dt + sqrt(2 T dt) ξ_i
```

The integration uses a fixed nominal model step of 0.012 and subdivides it when needed based on effective field stiffness. Ferromagnetic starting states are pre-relaxed for 700 zero-temperature steps before the experiment begins. Reset uses the same fixed random seed and initial configuration. Gaussian sampling uses a seeded JavaScript generator; its random sequence is different from NumPy's, but it represents the same distribution.

Time, temperature, field strength, and energy are **dimensionless model quantities**. The model is intended for qualitative demonstrations of collective ordering, remanence, and thermal disorder. It does not predict physical Curie temperatures, real-time relaxation constants, or quantitative hysteresis loops; it is not a quantum-mechanical simulation.

## Project files

- `index.html` — English interface and controls.
- `main.js` — complete physics model, field calculation, animation, and canvas rendering.
- `style.css` — responsive styling.

## Further reading

- [Fidimag: Core equations](https://fidimag.readthedocs.io/en/latest/physics_num_methods/core_eqs.html)
- [NIST OOMMF: Energy terms](https://math.nist.gov/oommf/doc/userguide21a2/userguide-xml/sec_oxsEnergies.html)
