"""Reduziertes PyScript-Applet zur longitudinalen Schallausbreitung.

Physikalisches Kernmodell
-------------------------
Das sichtbare zweidimensionale Gitter ist eine Darstellung von Material-
schichten. Alle Punkte einer Spalte besitzen dieselbe longitudinale Auslenkung
u_j. Dynamisch berechnet wird ausschließlich

    m * u_j'' = k * (u_(j+1) - 2*u_j + u_(j-1)).

Es gibt keine Querbewegung, Diagonalfedern, thermische Bewegung oder
Hintergrundstabilisierung. Die lokale Graustufe codiert kinetische plus
anteilig zugeordnete Federenergie.

Die optionale Kontinuumsnäherung wird nicht aus den Gitterwerten interpoliert.
Sie nutzt für die gleiche Randanregung die Lösung der Wellengleichung mit
c=a*sqrt(k/m). Neben der einlaufenden Welle wird die erste Reflexion am rechten
Rand berücksichtigt: mit Vorzeichenwechsel am festen und ohne Vorzeichenwechsel
am freien Ende. Daher kann die Abweichung des diskreten, dispersiven Modells
direkt sichtbar werden.
"""

from math import cos, pi, sin, sqrt

from js import document, window
from pyodide.ffi import create_proxy


# ---------------------------------------------------------------------------
# DOM-Hilfen
# ---------------------------------------------------------------------------


def el(element_id):
    element = document.getElementById(element_id)
    if element is None or type(element).__name__ in ("JsNull", "JsUndefined"):
        return None
    return element


def number(element_id, default):
    element = el(element_id)
    return float(element.value) if element is not None else default


def checked(element_id):
    element = el(element_id)
    return bool(element.checked) if element is not None else False


def set_text(element_id, value):
    element = el(element_id)
    if element is not None:
        element.textContent = str(value)


# ---------------------------------------------------------------------------
# Modellzustand
# ---------------------------------------------------------------------------


COLS = 25
ROWS = 8
SPACING = 1.0
BASE_DT = 0.006
PULSE_DURATION = 1.60
ENERGY_DISPLAY_REFERENCE = 0.14

u = [0.0] * COLS
v = [0.0] * COLS
acc = [0.0] * COLS

model_time = 0.0
is_running = False
last_timestamp = None
accumulator = 0.0

pulse_start = None
pulse_amplitude = 0.30
driver_phase_start = 0.0
driver_was_active = False

current_k = 4.0
current_m = 1.0
current_speed = 1.0
current_boundary = "absorbing"
current_frequency = 0.20

sim_canvas = el("sim_canvas")
profile_canvas = el("profile_canvas")
sim_ctx = sim_canvas.getContext("2d")
profile_ctx = profile_canvas.getContext("2d")

_proxies = []


def read_parameters():
    global current_k, current_m, current_speed, current_boundary, current_frequency
    current_k = number("stiffness_slider", 4.0)
    current_m = number("mass_slider", 1.0)
    current_speed = number("speed_slider", 1.0)
    current_frequency = number("frequency_slider", 0.20)
    selector = el("boundary_select")
    current_boundary = str(selector.value) if selector is not None else "absorbing"


# ---------------------------------------------------------------------------
# Anregung und Dynamik
# ---------------------------------------------------------------------------


def raised_cosine_pulse(local_time, amplitude):
    """Glatter Hin-und-zurück-Puls mit u=0 und du/dt=0 an beiden Enden."""
    if local_time < 0.0 or local_time > PULSE_DURATION:
        return 0.0, 0.0
    phase = 2.0 * pi * local_time / PULSE_DURATION
    displacement = 0.5 * amplitude * (1.0 - cos(phase))
    velocity = amplitude * pi / PULSE_DURATION * sin(phase)
    return displacement, velocity


def source_state(time_value):
    """Vorgegebene Bewegung der linken Materialschicht."""
    if checked("driver_checkbox"):
        phase_time = time_value - driver_phase_start
        if phase_time < 0.0:
            return 0.0, 0.0
        omega = 2.0 * pi * current_frequency
        amplitude = number("amplitude_slider", 0.30) * 0.55
        return amplitude * sin(omega * phase_time), amplitude * omega * cos(omega * phase_time)

    if pulse_start is not None:
        return raised_cosine_pulse(time_value - pulse_start, pulse_amplitude)

    return 0.0, 0.0


def calculate_acceleration(time_value):
    """Federkräfte für einen Freiheitsgrad je Spalte berechnen."""
    source_u, source_v = source_state(time_value)
    u[0] = source_u
    v[0] = source_v
    acc[0] = 0.0

    factor = current_k / current_m
    for j in range(1, COLS - 1):
        acc[j] = factor * (u[j + 1] - 2.0 * u[j] + u[j - 1])

    last = COLS - 1
    if current_boundary == "fixed":
        # Die letzte sichtbare Materialschicht ist fest eingespannt.
        acc[last] = 0.0
    elif current_boundary == "absorbing":
        # Impedanzangepasster Dämpfer am Ende: Z=sqrt(k*m).
        damping = sqrt(current_k * current_m)
        acc[last] = (current_k * (u[last - 1] - u[last]) - damping * v[last]) / current_m
    else:
        # Freies Ende: rechts wirkt keine weitere Feder.
        acc[last] = factor * (u[last - 1] - u[last])


def physics_step(dt):
    """Symplektischer Euler-Schritt; robust und energiearm driftend."""
    global model_time
    calculate_acceleration(model_time)
    for j in range(1, COLS):
        v[j] += acc[j] * dt
        u[j] += v[j] * dt
    if current_boundary == "fixed":
        u[-1] = 0.0
        v[-1] = 0.0
    model_time += dt
    source_u, source_v = source_state(model_time)
    u[0], v[0] = source_u, source_v


def local_energies():
    """Gesamtenergie jeder Spalte; Federenergie wird hälftig zugeordnet."""
    energies = [0.5 * current_m * velocity * velocity for velocity in v]
    spring_total = 0.0
    for j in range(COLS - 1):
        spring_energy = 0.5 * current_k * (u[j + 1] - u[j]) ** 2
        spring_total += spring_energy
        energies[j] += 0.5 * spring_energy
        energies[j + 1] += 0.5 * spring_energy

    kinetic_total = 0.5 * current_m * sum(velocity * velocity for velocity in v)
    return energies, kinetic_total, spring_total


# ---------------------------------------------------------------------------
# Darstellung
# ---------------------------------------------------------------------------


def geometry(canvas):
    width = float(canvas.width)
    height = float(canvas.height)
    left, right = 62.0, width - 44.0
    top, bottom = 62.0, height - 54.0
    dx = (right - left) / (COLS - 1)
    dy = (bottom - top) / (ROWS - 1)
    return width, height, left, right, top, bottom, dx, dy


def draw_simulation():
    ctx = sim_ctx
    width, height, left, right, top, bottom, dx, dy = geometry(sim_canvas)
    ctx.clearRect(0, 0, width, height)

    ctx.fillStyle = "#fbfcfe"
    ctx.fillRect(0, 0, width, height)

    # Ruhelagen zeigen, dass die Spalten nur um feste Orte schwingen.
    ctx.strokeStyle = "#e4e8ef"
    ctx.lineWidth = 1
    ctx.setLineDash([3, 5])
    for j in range(COLS):
        x_rest = left + j * dx
        ctx.beginPath()
        ctx.moveTo(x_rest, top - 13)
        ctx.lineTo(x_rest, bottom + 13)
        ctx.stroke()
    ctx.setLineDash([])

    energies, _, _ = local_energies()
    # Am freien Ende kann sich die Auslenkungsamplitude bei der Reflexion
    # annähernd verdoppeln. Die Skalierung lässt dafür ausreichend Platz.
    amplitude_scale = 0.34 * dx / max(0.30, number("amplitude_slider", 0.30))
    xs = [left + j * dx + amplitude_scale * u[j] for j in range(COLS)]

    # Horizontale Federn/Bindungen. Vertikale Linien verdeutlichen die
    # gemeinsame Bewegung einer Materialschicht, erzeugen aber keine Kraft.
    ctx.strokeStyle = "#aeb7c5"
    ctx.lineWidth = 1.15
    for row in range(ROWS):
        y_pos = top + row * dy
        ctx.beginPath()
        ctx.moveTo(xs[0], y_pos)
        for j in range(1, COLS):
            ctx.lineTo(xs[j], y_pos)
        ctx.stroke()

    ctx.strokeStyle = "#d3d8e1"
    ctx.lineWidth = 1
    for j in range(COLS):
        ctx.beginPath()
        ctx.moveTo(xs[j], top)
        ctx.lineTo(xs[j], bottom)
        ctx.stroke()

    max_energy = max(max(energies), ENERGY_DISPLAY_REFERENCE)
    for j in range(COLS):
        intensity = min(1.0, sqrt(energies[j] / max_energy))
        grey = round(220 - 185 * intensity)
        ctx.fillStyle = f"rgb({grey},{grey},{grey})"
        for row in range(ROWS):
            y_pos = top + row * dy
            ctx.beginPath()
            ctx.arc(xs[j], y_pos, 5.1, 0, 2 * pi)
            ctx.fill()

    ctx.fillStyle = "#68758a"
    ctx.font = "13px system-ui, sans-serif"
    ctx.textAlign = "left"
    ctx.fillText("Anregung", left - 16, 29)
    ctx.textAlign = "right"
    ending = {"free": "freier Rand", "fixed": "fester Rand", "absorbing": "absorbierender Rand"}[current_boundary]
    ctx.fillText(ending, right + 15, 29)


def continuum_value(x_position):
    """Kontinuumslösung mit der ersten Reflexion am rechten Rand.

    Die einlaufende Welle besitzt die retardierte Zeit t-x/c. Der vom rechten
    Rand zurücklaufende Anteil hat den zusätzlichen Weg 2L-x. Am festen Ende
    wird die Auslenkung invertiert, am freien Ende bleibt ihr Vorzeichen
    erhalten. Der absorbierende Rand enthält idealerweise keinen reflektierten
    Anteil. Eine weitere Reflexion an der linken Quelle wird bewusst nicht
    modelliert.
    """
    wave_speed = SPACING * sqrt(current_k / current_m)
    length = (COLS - 1) * SPACING

    incident_time = model_time - x_position / wave_speed
    incident = source_state(incident_time)[0]

    if current_boundary == "absorbing":
        return incident

    reflected_time = model_time - (2.0 * length - x_position) / wave_speed
    reflected = source_state(reflected_time)[0]
    reflection_sign = -1.0 if current_boundary == "fixed" else 1.0
    return incident + reflection_sign * reflected


def draw_profile():
    ctx = profile_ctx
    width, height = float(profile_canvas.width), float(profile_canvas.height)
    left, right, top, bottom = 58.0, width - 28.0, 28.0, height - 42.0
    mid = 0.5 * (top + bottom)
    x_scale = (right - left) / (COLS - 1)
    amplitude = max(0.30, number("amplitude_slider", 0.30))
    # Beim freien Ende kann einfallende plus reflektierte Welle die doppelte
    # Auslenkungsamplitude erreichen.
    y_scale = 0.22 * (bottom - top) / amplitude

    ctx.clearRect(0, 0, width, height)
    ctx.fillStyle = "#fbfcfe"
    ctx.fillRect(0, 0, width, height)

    ctx.strokeStyle = "#d7dde7"
    ctx.lineWidth = 1
    ctx.beginPath()
    ctx.moveTo(left, mid)
    ctx.lineTo(right, mid)
    ctx.stroke()

    ctx.fillStyle = "#68758a"
    ctx.font = "12px system-ui, sans-serif"
    ctx.textAlign = "right"
    ctx.fillText("0", left - 9, mid + 4)
    ctx.textAlign = "center"
    ctx.fillText("Position im Festkörper", 0.5 * (left + right), height - 13)

    if checked("continuum_checkbox"):
        ctx.strokeStyle = "#8a94a5"
        ctx.lineWidth = 2.2
        ctx.setLineDash([8, 6])
        ctx.beginPath()
        sample_count = 240
        for sample in range(sample_count):
            fraction = sample / (sample_count - 1)
            x_model = fraction * (COLS - 1) * SPACING
            px = left + fraction * (right - left)
            py = mid - y_scale * continuum_value(x_model)
            if sample == 0:
                ctx.moveTo(px, py)
            else:
                ctx.lineTo(px, py)
        ctx.stroke()
        ctx.setLineDash([])

    ctx.strokeStyle = "#202632"
    ctx.lineWidth = 2.4
    ctx.beginPath()
    for j in range(COLS):
        px = left + j * x_scale
        py = mid - y_scale * u[j]
        if j == 0:
            ctx.moveTo(px, py)
        else:
            ctx.lineTo(px, py)
    ctx.stroke()

    ctx.fillStyle = "#202632"
    for j in range(COLS):
        ctx.beginPath()
        ctx.arc(left + j * x_scale, mid - y_scale * u[j], 2.7, 0, 2 * pi)
        ctx.fill()


def update_time():
    set_text("time_value", f"{model_time:.2f}")


def draw_all():
    draw_simulation()
    draw_profile()
    update_time()


# ---------------------------------------------------------------------------
# Bedienung und Animation
# ---------------------------------------------------------------------------


def reset_state(event=None):
    global model_time, pulse_start, last_timestamp, accumulator, driver_phase_start
    for j in range(COLS):
        u[j] = v[j] = acc[j] = 0.0
    model_time = 0.0
    pulse_start = None
    driver_phase_start = 0.0
    last_timestamp = None
    accumulator = 0.0
    set_text("status_text", "bereit" if not is_running else "läuft")
    draw_all()


def send_pulse(event=None):
    global pulse_start, pulse_amplitude, is_running, last_timestamp
    pulse_start = model_time
    pulse_amplitude = number("amplitude_slider", 0.30)
    is_running = True
    last_timestamp = None
    set_text("status_text", "Puls läuft")
    set_text("play_button", "Ⅱ Pause")


def toggle_play(event=None):
    global is_running, last_timestamp
    is_running = not is_running
    last_timestamp = None
    set_text("play_button", "Ⅱ Pause" if is_running else "▶ Start")
    set_text("status_text", "läuft" if is_running else "Pause")


def on_parameter_change(event=None):
    read_parameters()
    set_text("stiffness_value", f"{current_k:.1f}")
    set_text("mass_value", f"{current_m:.1f}")
    set_text("amplitude_value", f"{number('amplitude_slider', 0.30):.2f}")
    set_text("speed_value", f"{current_speed:.2f}×")
    set_text("frequency_value", f"{current_frequency:.2f}")
    legend = el("continuum_legend")
    if legend is not None:
        legend.hidden = not checked("continuum_checkbox")
    draw_all()


def on_driver_change(event=None):
    global driver_phase_start, driver_was_active, pulse_start, is_running, last_timestamp
    active = checked("driver_checkbox")
    if active and not driver_was_active:
        driver_phase_start = model_time
        pulse_start = None
        is_running = True
        last_timestamp = None
        set_text("play_button", "Ⅱ Pause")
        set_text("status_text", "Signalgenerator")
    driver_was_active = active
    on_parameter_change()


def animation_frame(timestamp):
    global last_timestamp, accumulator
    read_parameters()

    if last_timestamp is None:
        last_timestamp = float(timestamp)
    elapsed = min(0.05, max(0.0, (float(timestamp) - last_timestamp) / 1000.0))
    last_timestamp = float(timestamp)

    if is_running:
        # Die Modellzeit wird unabhängig von der Bildrate in festen Schritten
        # integriert. Der Temposlider skaliert nur die verstrichene Modellzeit.
        accumulator += elapsed * current_speed
        steps = 0
        while accumulator >= BASE_DT and steps < 40:
            physics_step(BASE_DT)
            accumulator -= BASE_DT
            steps += 1
        if pulse_start is not None and model_time > pulse_start + PULSE_DURATION and not checked("driver_checkbox"):
            set_text("status_text", "läuft")

    draw_all()
    window.requestAnimationFrame(animation_proxy)


def bind(element_id, event_name, handler):
    element = el(element_id)
    if element is None:
        return
    proxy = create_proxy(handler)
    _proxies.append(proxy)
    element.addEventListener(event_name, proxy)


bind("pulse_button", "click", send_pulse)
bind("play_button", "click", toggle_play)
bind("reset_button", "click", reset_state)

for slider_id in ("stiffness_slider", "mass_slider", "amplitude_slider", "speed_slider", "frequency_slider"):
    bind(slider_id, "input", on_parameter_change)

bind("boundary_select", "change", on_parameter_change)
bind("continuum_checkbox", "change", on_parameter_change)
bind("driver_checkbox", "change", on_driver_change)

read_parameters()
draw_all()
animation_proxy = create_proxy(animation_frame)
_proxies.append(animation_proxy)
window.requestAnimationFrame(animation_proxy)
