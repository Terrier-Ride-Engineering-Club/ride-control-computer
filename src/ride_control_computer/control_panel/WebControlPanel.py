# Web-based ControlPanel for TREC's REC Ride Control Computer
# Made by Jackson Justus (jackjust@bu.edu)
#
# Implements the full ControlPanel interface (callbacks, indicator blink logic)
# over HTTP so the ride can be operated from a browser without physical RCP
# hardware.  Runs a Flask/Waitress server in the run() daemon thread.
#
# Indicator state is polled by the browser at GET /api/state every 250 ms.
# Button events are fired via POST /api/button/<name>, /api/power, /api/jog.

import logging
import threading

from flask import Flask, jsonify, request
from waitress import serve

from ride_control_computer.RCC import RCCState
from ride_control_computer.control_panel.ControlPanel import (
    ControlPanel,
    MomentaryButtonState,
    MomentarySwitchState,
    SustainedSwitchState,
)

logger = logging.getLogger(__name__)

# Indicator mode strings sent to the browser (must match CSS class names in HTML)
_MODE_OFF        = "off"
_MODE_BLINK      = "blink"
_MODE_BLINK_FAST = "blink_fast"

# Blink timing (ms) — kept in sync with HardwareControlPanel constants
_BLINK_MS      = 500
_BLINK_FAST_MS = 100

# ─── Static control panel page ────────────────────────────────────────────────

_HTML = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
  <title>RCC Control Panel</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: 'Segoe UI', system-ui, sans-serif;
      background: #111;
      color: #eee;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 20px;
      padding: 16px;
    }}

    /* ── Status bar ── */
    #statusBar {{
      width: 100%;
      max-width: 500px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      background: #1e1e1e;
      border-radius: 8px;
      padding: 10px 16px;
    }}
    #rccState {{ font-weight: 700; font-size: 18px; letter-spacing: .05em; }}
    #faultBadge {{
      background: #c0392b;
      color: #fff;
      padding: 3px 10px;
      border-radius: 4px;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: .08em;
      visibility: hidden;
    }}
    #faultBadge.active {{ visibility: visible; }}

    /* ── Panels ── */
    .panel {{
      width: 100%;
      max-width: 500px;
      background: #1e1e1e;
      border-radius: 10px;
      padding: 16px;
    }}
    .panel h2 {{
      font-size: 10px;
      letter-spacing: .14em;
      text-transform: uppercase;
      color: #666;
      margin-bottom: 12px;
    }}

    /* ── Key switch ── */
    #powerSwitch {{ display: flex; gap: 8px; }}
    .power-btn {{
      flex: 1;
      padding: 12px 0;
      border: 2px solid #333;
      border-radius: 6px;
      background: #2a2a2a;
      color: #888;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      transition: background .15s, border-color .15s, color .15s;
    }}
    .power-btn.active {{ background: #1a3d1a; border-color: #4caf50; color: #fff; }}
    .power-btn:active  {{ filter: brightness(1.25); }}

    /* ── Indicator LEDs ── */
    .btn-wrap {{ flex: 1; display: flex; flex-direction: column; align-items: center; gap: 8px; }}
    .indicator {{
      width: 14px; height: 14px;
      border-radius: 50%;
      background: #2a2a2a;
      border: 2px solid #444;
    }}
    .indicator.on {{
      background: #f5f5f5;
      border-color: #fff;
      box-shadow: 0 0 6px #ffffff88;
    }}
    @keyframes blinkAnim     {{ 0%,49%{{opacity:1}} 50%,100%{{opacity:0}} }}
    @keyframes blinkFastAnim {{ 0%,49%{{opacity:1}} 50%,100%{{opacity:0}} }}
    .indicator.blink      {{
      background: #f5f5f5; border-color: #fff;
      animation: blinkAnim     {_BLINK_MS}ms step-start infinite;
    }}
    .indicator.blink_fast {{
      background: #f5f5f5; border-color: #fff;
      animation: blinkFastAnim {_BLINK_FAST_MS}ms step-start infinite;
    }}

    /* ── Op buttons ── */
    #opButtons {{ display: flex; gap: 12px; }}
    .op-btn {{
      width: 100%;
      padding: 22px 0;
      border: none;
      border-radius: 8px;
      font-size: 14px;
      font-weight: 700;
      letter-spacing: .05em;
      cursor: pointer;
      user-select: none; -webkit-user-select: none;
    }}
    .op-btn:active {{ filter: brightness(1.3); }}
    #btn-dispatch {{ background: #27ae60; color: #fff; }}
    #btn-reset    {{ background: #e67e22; color: #fff; }}
    #btn-stop     {{ background: #546e7a; color: #fff; }}

    /* ── E-Stop ── */
    #estopBtn {{
      width: 100%;
      padding: 32px 0;
      border: none;
      border-radius: 8px;
      background: #c0392b;
      color: #fff;
      font-size: 24px;
      font-weight: 900;
      letter-spacing: .12em;
      cursor: pointer;
      user-select: none; -webkit-user-select: none;
    }}
    #estopBtn:active {{ filter: brightness(1.2); }}

    /* ── Jog ── */
    #jogSection {{ display: none; }}
    #jogButtons {{ display: flex; gap: 16px; }}
    .jog-btn {{
      flex: 1;
      padding: 32px 0;
      border: none;
      border-radius: 8px;
      background: #263238;
      color: #fff;
      font-size: 16px;
      font-weight: 700;
      cursor: pointer;
      user-select: none; -webkit-user-select: none;
    }}
    .jog-btn:active {{ filter: brightness(1.3); }}
  </style>
</head>
<body>

  <div id="statusBar">
    <span id="rccState">—</span>
    <span id="faultBadge">FAULT</span>
  </div>

  <div class="panel">
    <h2>Key Switch</h2>
    <div id="powerSwitch">
      <button class="power-btn" id="pw-off"   onclick="setPower('off')">OFF</button>
      <button class="power-btn" id="pw-on"    onclick="setPower('on')">ON</button>
      <button class="power-btn" id="pw-maint" onclick="setPower('maintenance')">MAINT</button>
    </div>
  </div>

  <div class="panel">
    <h2>Operator Controls</h2>
    <div id="opButtons">
      <div class="btn-wrap">
        <div class="indicator" id="ind-dispatch"></div>
        <button id="btn-dispatch" class="op-btn">DISPATCH</button>
      </div>
      <div class="btn-wrap">
        <div class="indicator" id="ind-reset"></div>
        <button id="btn-reset" class="op-btn">RESET</button>
      </div>
      <div class="btn-wrap">
        <div class="indicator" id="ind-stop"></div>
        <button id="btn-stop" class="op-btn">STOP</button>
      </div>
    </div>
  </div>

  <div class="panel">
    <button id="estopBtn">&#9889; E-STOP</button>
  </div>

  <div class="panel" id="jogSection">
    <h2>Maintenance Jog</h2>
    <div id="jogButtons">
      <button class="jog-btn" id="btn-jog-up">&#9650; JOG UP</button>
      <button class="jog-btn" id="btn-jog-down">&#9660; JOG DOWN</button>
    </div>
  </div>

<script>
  const POLL_MS = 250;

  // Map RCC state names to the active power button id.
  // Anything not listed here defaults to "pw-on".
  const POWER_BTN = {{ OFF: "pw-off", MAINTENANCE: "pw-maint" }};

  let _held = new Set();  // buttons currently pressed by the user

  // ── API polling ──────────────────────────────────────────────────────────────
  function poll() {{
    fetch("/api/state")
      .then(r => r.json())
      .then(d => {{
        document.getElementById("rccState").textContent = d.rccState;
        document.getElementById("faultBadge").classList.toggle("active", d.hasActiveFaults);

        // Indicator modes
        for (const [name, mode] of Object.entries(d.indicators)) {{
          const el = document.getElementById("ind-" + name);
          if (el) el.className = "indicator " + mode;
        }}

        // Key switch highlight
        ["pw-off","pw-on","pw-maint"].forEach(id =>
          document.getElementById(id).classList.remove("active"));
        document.getElementById(POWER_BTN[d.rccState] ?? "pw-on").classList.add("active");

        // Jog section visibility
        document.getElementById("jogSection").style.display =
          d.rccState === "MAINTENANCE" ? "block" : "none";
      }})
      .catch(() => {{}});
  }}
  setInterval(poll, POLL_MS);
  poll();

  // ── HTTP helpers ─────────────────────────────────────────────────────────────
  function post(url, body) {{
    fetch(url, {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify(body),
    }}).catch(() => {{}});
  }}

  // ── Button wiring ─────────────────────────────────────────────────────────────
  function pressBtn(name) {{
    if (_held.has(name)) return;
    _held.add(name);
    post("/api/button/" + name, {{ pressed: true }});
  }}
  function releaseBtn(name) {{
    if (!_held.has(name)) return;
    _held.delete(name);
    post("/api/button/" + name, {{ pressed: false }});
  }}
  function setPower(position) {{ post("/api/power", {{ position }}); }}
  function setJog(direction)  {{ post("/api/jog",   {{ direction }}); }}

  function wireOpBtn(id, name) {{
    const btn = document.getElementById(id);
    btn.addEventListener("mousedown",   () => pressBtn(name));
    btn.addEventListener("mouseup",     () => releaseBtn(name));
    btn.addEventListener("mouseleave",  () => releaseBtn(name));
    btn.addEventListener("touchstart",  e  => {{ e.preventDefault(); pressBtn(name); }});
    btn.addEventListener("touchend",    e  => {{ e.preventDefault(); releaseBtn(name); }});
    btn.addEventListener("touchcancel", e  => {{ e.preventDefault(); releaseBtn(name); }});
  }}

  wireOpBtn("btn-dispatch", "dispatch");
  wireOpBtn("btn-reset",    "reset");
  wireOpBtn("btn-stop",     "stop");
  wireOpBtn("estopBtn",     "estop");

  function wireJogBtn(id, direction) {{
    const btn = document.getElementById(id);
    btn.addEventListener("mousedown",   () => setJog(direction));
    btn.addEventListener("mouseup",     () => setJog("neutral"));
    btn.addEventListener("mouseleave",  () => setJog("neutral"));
    btn.addEventListener("touchstart",  e  => {{ e.preventDefault(); setJog(direction); }});
    btn.addEventListener("touchend",    e  => {{ e.preventDefault(); setJog("neutral"); }});
    btn.addEventListener("touchcancel", e  => {{ e.preventDefault(); setJog("neutral"); }});
  }}

  wireJogBtn("btn-jog-up",   "up");
  wireJogBtn("btn-jog-down", "down");
</script>
</body>
</html>"""


# ─── WebControlPanel ──────────────────────────────────────────────────────────

class WebControlPanel(ControlPanel):
    """
    ControlPanel implementation served over HTTP.

    Provides the full operator interface (dispatch, reset, stop, e-stop, key
    switch, maintenance jog) through a browser UI so the ride can be driven
    with motor-controller hardware but without a physical RCP.

    The panel page is static HTML; all dynamic data flows through a lightweight
    JSON polling API.  Indicator blink logic mirrors HardwareControlPanel —
    the browser renders the mode via CSS animations.

    Threading model:
      - run()             → blocks in Waitress (called in a daemon thread by RCC)
      - updateIndicators()→ called by RCC main thread; writes under _stateLock
      - Flask handlers    → run in Waitress worker threads; read under _stateLock
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 5001):
        """
        Args:
            host: Address to bind to.  "0.0.0.0" (default) accepts connections
                  from any device on the network (e.g. operator's tablet).
            port: TCP port.  Defaults to 5001 to avoid colliding with the
                  existing telemetry webserver (Waitress default 8080).
        """
        super().__init__()
        self._host = host
        self._port = port
        self._app  = Flask(__name__)

        # Shared state — written by RCC thread, read by Flask threads
        self._stateLock      = threading.Lock()
        self._rccStateName   = "UNKNOWN"
        self._hasActiveFaults = False
        self._indicatorModes  = {
            "dispatch": _MODE_OFF,
            "reset":    _MODE_OFF,
            "stop":     _MODE_OFF,
        }

        self._registerRoutes()

    # =========================================================================
    #                           INDICATOR UPDATE
    # =========================================================================

    def updateIndicators(self, state, hasActiveFaults: bool, onlyMCEstopFault: bool = False) -> None:
        """Called by the RCC main thread each loop tick. Thread-safe."""
        dispatchMode = _MODE_BLINK if state == RCCState.IDLE else _MODE_OFF
        resetMode    = (
            _MODE_BLINK if (state == RCCState.ESTOP and not hasActiveFaults)
            else _MODE_OFF
        )
        stopMode = _MODE_BLINK_FAST if state == RCCState.STOPPING else _MODE_OFF

        with self._stateLock:
            self._rccStateName    = state.name
            self._hasActiveFaults = hasActiveFaults
            self._indicatorModes  = {
                "dispatch": dispatchMode,
                "reset":    resetMode,
                "stop":     stopMode,
            }

    # =========================================================================
    #                           LIFECYCLE
    # =========================================================================

    def run(self) -> None:
        """Blocking call — runs the Waitress server.  Called in a daemon thread by RCC."""
        logger.info("WebControlPanel listening on http://%s:%d", self._host, self._port)
        serve(self._app, host=self._host, port=self._port, threads=4)

    # =========================================================================
    #                           FLASK ROUTES
    # =========================================================================

    def _registerRoutes(self) -> None:
        app = self._app

        @app.route("/")
        def index():
            return _HTML

        @app.route("/api/state")
        def apiState():
            with self._stateLock:
                return jsonify({
                    "rccState":        self._rccStateName,
                    "hasActiveFaults": self._hasActiveFaults,
                    "indicators":      dict(self._indicatorModes),
                })

        @app.route("/api/button/<name>", methods=["POST"])
        def apiButton(name: str):
            data    = request.get_json(silent=True) or {}
            pressed = data.get("pressed", True)
            btnState = (MomentaryButtonState.PRESSED if pressed
                        else MomentaryButtonState.RELEASED)

            dispatchers = {
                "dispatch": self._enqueueDispatch,
                "reset":    self._enqueueReset,
                "stop":     self._enqueueStop,
                "estop":    self._enqueueEstop,
            }
            if name not in dispatchers:
                return jsonify({"error": f"Unknown button: {name}"}), 400
            dispatchers[name](btnState)
            return jsonify({"ok": True})

        @app.route("/api/power", methods=["POST"])
        def apiPower():
            data     = request.get_json(silent=True) or {}
            position = data.get("position", "")
            mapping  = {
                "on":          SustainedSwitchState.ON,
                "off":         SustainedSwitchState.OFF,
                "maintenance": SustainedSwitchState.MAINTENANCE,
            }
            if position not in mapping:
                return jsonify({"error": f"Unknown position: {position}"}), 400
            self._enqueueMaintenanceSwitch(mapping[position])
            return jsonify({"ok": True})

        @app.route("/api/jog", methods=["POST"])
        def apiJog():
            data      = request.get_json(silent=True) or {}
            direction = data.get("direction", "neutral")
            mapping   = {
                "up":      MomentarySwitchState.UP,
                "neutral": MomentarySwitchState.NEUTRAL,
                "down":    MomentarySwitchState.DOWN,
            }
            if direction not in mapping:
                return jsonify({"error": f"Unknown direction: {direction}"}), 400
            self._enqueueMaintenanceJogSwitch(mapping[direction])
            return jsonify({"ok": True})
