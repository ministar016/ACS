"""
SimBus — Qt bridge between the QML dashboard and the simulation process.

Architecture
────────────
  GUI process                                  simulation process (sim/worker.py)
  ───────────                                  ─────────────────────────────────
  QML ──slot──▶ SimBus ──("cmd", …)──Pipe──▶   SimEngine (scenario, editor,
  QML ◀─signal── SimBus ◀──("frame", …)─────    drivability, artemides link)
                 └ QTimer 30 ms: drain pipe,
                   emit the newest frame

The GUI never runs a simulation step, so the dashboard stays responsive at
any speed; the worker paces the sim and decides how often to send frames
(every 5th … 50th step, see sim/worker.py).  Signals carry plain
dicts/lists that QML maps to its properties — the same payloads as before
the split, so the QML side did not change.

Usage
─────
    bus = SimBus()
    engine.rootContext().setContextProperty("simBus", bus)
    bus.start()
"""
from __future__ import annotations
import multiprocessing as mp
import sys
from PyQt6.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot, QVariant

from .worker import worker_main

_DRAIN_MS = 30


class SimBus(QObject):
    # ── Signals ───────────────────────────────────────────────────────────
    timeUpdated     = pyqtSignal(float)
    uavsUpdated     = pyqtSignal(QVariant)   # interceptors (incl. idle on the pad)
    ugvsUpdated     = pyqtSignal(QVariant)
    acousticUpdated = pyqtSignal(QVariant)
    seismicUpdated  = pyqtSignal(QVariant)
    tracksUpdated   = pyqtSignal(QVariant)   # fused tracks, most urgent first
    threatUpdated   = pyqtSignal(int)
    targetsUpdated  = pyqtSignal(QVariant)   # ground truth (debug overlay)

    zoneUpdated        = pyqtSignal(QVariant)
    laydownUpdated     = pyqtSignal(QVariant)
    engagementsUpdated = pyqtSignal(QVariant)
    eventsUpdated      = pyqtSignal(QVariant)
    linkUpdated        = pyqtSignal(QVariant)
    autoRoeChanged     = pyqtSignal(bool)
    pvoUpdated         = pyqtSignal(QVariant)   # {enabled, ggEnabled, sites, gg, munitions}
    statsUpdated       = pyqtSignal(QVariant)   # {kills, baseHits, assaults}
    enemyRouteUpdated  = pyqtSignal(QVariant)   # convoy route (ground truth, TRUTH overlay only)
    detectionsUpdated  = pyqtSignal(QVariant)   # recent acoustic / seismic bearing detections

    # Editor / scenarios / drivability / catalog / performance
    editModeChanged     = pyqtSignal(bool)
    editResult          = pyqtSignal(QVariant)   # {ok, message}
    scenariosUpdated    = pyqtSignal(QVariant)   # [names]
    drivabilityUpdated  = pyqtSignal(QVariant)   # {status, url, bbox, legend, stats}
    catalogUpdated      = pyqtSignal(QVariant)   # systems catalog (sim/systems.py)
    perfUpdated         = pyqtSignal(QVariant)   # {speed, effective, stepMs, displayEvery}
    backendUpdated      = pyqtSignal(QVariant)   # {alive, message}
    borderUpdated       = pyqtSignal(QVariant)   # {lines: [[{lat, lon}]], source}
    readinessUpdated    = pyqtSignal(QVariant)   # {phase, axes, uavStations, ugvStations, war, warT}

    def __init__(self, dt: float = 0.1, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._dt = dt
        ctx = mp.get_context("spawn")             # same on macOS / Linux / Windows; no forked Qt state
        self._conn, child = ctx.Pipe(duplex=True)
        self._proc = ctx.Process(target=worker_main, args=(child, dt, list(sys.path)),
                                 name="amcs-sim", daemon=True)
        self._child = child
        self._drain = QTimer(self)
        self._drain.setInterval(_DRAIN_MS)
        self._drain.timeout.connect(self._drain_pipe)
        self._closed = False

    # ── process / pipe ────────────────────────────────────────────────────

    def start(self) -> None:
        self._proc.start()
        self._child.close()
        self._drain.start()

    def _send(self, *msg) -> None:
        if self._closed:
            return
        try:
            self._conn.send(msg)
        except (BrokenPipeError, OSError):
            self._backend_lost()

    def _cmd(self, name: str, *args) -> None:
        self._send("cmd", name, args)

    def _drain_pipe(self) -> None:
        """Take everything waiting; emit each signal once with its newest payload."""
        latest: dict[str, object] = {}
        try:
            while self._conn.poll():
                msg = self._conn.recv()
                if msg[0] == "frame":
                    for name, payload in msg[1]:
                        latest.pop(name, None)
                        latest[name] = payload
        except (EOFError, OSError):
            self._backend_lost()
        for name, payload in latest.items():
            sig = getattr(self, name, None)
            if sig is not None:
                sig.emit(payload)
        if not self._proc.is_alive() and not self._closed:
            self._backend_lost()

    def _backend_lost(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._drain.stop()
        code = self._proc.exitcode
        print(f"[amcs] simulation process ended (exit code {code})", file=sys.stderr)
        self.backendUpdated.emit({"alive": False, "message": f"simulation process ended ({code})"})

    @pyqtSlot()
    def shutdown(self) -> None:
        """Stop the worker; it retracts anything published to artemides-trax first."""
        if self._closed:
            return
        self._drain.stop()
        try:
            self._conn.send(("shutdown",))
            if self._conn.poll(35.0):              # threat-marker deletes may take a while
                self._conn.recv()
        except (BrokenPipeError, EOFError, OSError):
            pass
        self._closed = True
        self._proc.join(5.0)
        if self._proc.is_alive():
            self._proc.terminate()

    # ── Simulation control ────────────────────────────────────────────────

    @pyqtSlot()
    def stop(self) -> None:
        self._cmd("stop")

    @pyqtSlot()
    def reset(self) -> None:
        self._cmd("reset")

    @pyqtSlot(int)
    def setTimeScale(self, scale: int) -> None:
        """Simulation time multiplier (1×, 2×, 5×, 10×, 20×, 50×)."""
        self._send("speed", scale)

    # ── Operator: engagements ─────────────────────────────────────────────

    @pyqtSlot()
    def acceptMission(self) -> None:
        self._cmd("acceptMission")

    @pyqtSlot(str)
    def approveEngagement(self, eng_id: str) -> None:
        self._cmd("approveEngagement", eng_id)

    @pyqtSlot(str)
    def denyEngagement(self, eng_id: str) -> None:
        self._cmd("denyEngagement", eng_id)

    @pyqtSlot(str)
    def abortEngagement(self, eng_id: str) -> None:
        self._cmd("abortEngagement", eng_id)

    @pyqtSlot()
    def abortAll(self) -> None:
        self._cmd("abortAll")

    @pyqtSlot(bool)
    def setPvoEnabled(self, enabled: bool) -> None:
        self._cmd("setPvoEnabled", enabled)

    @pyqtSlot(bool)
    def setAutoRoe(self, enabled: bool) -> None:
        self._cmd("setAutoRoe", enabled)

    # ── Operator: interceptors on call ────────────────────────────────────

    @pyqtSlot(str)
    def launchInterceptor(self, device_id: str) -> None:
        self._cmd("launchInterceptor", device_id)

    @pyqtSlot(str)
    def recallInterceptor(self, device_id: str) -> None:
        self._cmd("recallInterceptor", device_id)

    # ── Scenario editor ───────────────────────────────────────────────────

    @pyqtSlot(bool)
    def setEditMode(self, on: bool) -> None:
        self._cmd("setEditMode", on)

    @pyqtSlot(str, float, float)
    def editPlace(self, tool: str, lat: float, lon: float) -> None:
        self._cmd("editPlace", tool, lat, lon)

    @pyqtSlot(str, str)
    def setPlaceSystem(self, kind: str, code: str) -> None:
        self._cmd("setPlaceSystem", kind, code)

    @pyqtSlot()
    def cancelMove(self) -> None:
        self._cmd("cancelMove")

    @pyqtSlot(float)
    def setZoneRadius(self, radius_m: float) -> None:
        self._cmd("setZoneRadius", radius_m)

    @pyqtSlot(int)
    def setInterceptors(self, n: int) -> None:
        self._cmd("setInterceptors", n)

    @pyqtSlot(int, int, int)
    def setConvoy(self, vehicles: int, escorts: int, aviation: int) -> None:
        self._cmd("setConvoy", vehicles, escorts, aviation)

    @pyqtSlot(str)
    def saveScenario(self, name: str) -> None:
        self._cmd("saveScenario", name)

    @pyqtSlot(str)
    def loadScenario(self, name: str) -> None:
        self._cmd("loadScenario", name)

    @pyqtSlot()
    def refreshScenarios(self) -> None:
        self._cmd("refreshScenarios")

    # ── Drivability layer ─────────────────────────────────────────────────

    @pyqtSlot(bool)
    def loadDrivability(self, refresh: bool) -> None:
        self._cmd("loadDrivability", refresh)
