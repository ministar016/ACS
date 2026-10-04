"""
Simulation worker process — runs SimEngine apart from the GUI.

Python runs one thread at a time per process, so a simulation stepping in the
GUI process freezes the dashboard whenever a batch of steps takes longer
than a frame.  Here the engine has its own process (its own CPU core); the
GUI only receives frames and draws them.

Pacing
──────
Wall-clock paced: at speed N the sim advances N × dt of sim time per dt of
wall time.  When the CPU cannot keep up (heavy phase at 50×), the worker
simply runs flat out — the requested speed becomes "as fast as possible" and
the achieved speed is reported, instead of the GUI locking up.

Display decimation
──────────────────
A frame (all GUI payloads of one moment) is sent every `display_every`
steps: max(5, speed) → every 5th step at 1–5×, every 10th at 10×, every 50th
at 50×, i.e. ≈ 2–10 frames per second whatever the speed.  If stepping is so
slow that this would leave the screen still for longer than MAX_FRAME_GAP_S,
a frame is sent anyway.  Commands from the GUI are handled between steps and
their results are sent at once.

Protocol (multiprocessing Pipe, pickled tuples)
───────────────────────────────────────────────
  GUI → worker   ("cmd", name, args)            SimEngine command
                 ("speed", n)                   time multiplier 1…50
                 ("shutdown",)
  worker → GUI   ("frame", [(signal, payload), …])
                 ("bye",)
"""
from __future__ import annotations
import os
import sys
import time
import traceback

MAX_SPEED       = 50
MAX_FRAME_GAP_S = 0.5      # never leave the screen still longer than this
POLL_S          = 0.005
JOB_POLL_S      = 0.25     # drivability download progress


def display_every(speed: int) -> int:
    return max(5, speed)


class _FrameBuffer:
    """Collects emitted signals; the latest payload per signal wins."""

    def __init__(self) -> None:
        self.items: dict[str, object] = {}

    def __call__(self, name: str, payload) -> None:
        self.items.pop(name, None)            # keep emission order of the latest values
        self.items[name] = payload

    def take(self) -> list[tuple[str, object]]:
        out, self.items = list(self.items.items()), {}
        return out


def worker_main(conn, dt: float = 0.1, sys_path: list[str] | None = None) -> None:
    if sys_path:
        sys.path[:0] = [p for p in sys_path if p not in sys.path]
    from sim.engine import SimEngine

    buf = _FrameBuffer()
    engine = SimEngine(dt=dt, emit=buf)
    speed = 1
    steps_since_frame = 0
    t_last_frame = time.perf_counter()
    t_last_jobs = 0.0
    # pacing anchor: (wall time, sim time) the schedule is measured from
    anchor = (time.perf_counter(), 0.0)
    perf = {"stepMs": 0.0, "effective": 0.0, "speed": speed, "displayEvery": display_every(speed)}
    eff_window = [(time.perf_counter(), 0.0)]

    def flush() -> None:
        nonlocal steps_since_frame, t_last_frame
        items = buf.take()
        if items:
            conn.send(("frame", items))
        steps_since_frame = 0
        t_last_frame = time.perf_counter()

    def rebase() -> None:
        nonlocal anchor
        anchor = (time.perf_counter(), engine.sim_time)

    engine.start()
    flush()
    try:
        while True:
            # ── commands ─────────────────────────────────────────────────
            behind = engine.running and \
                engine.sim_time < anchor[1] + (time.perf_counter() - anchor[0]) * speed
            while conn.poll(0 if behind else POLL_S):
                msg = conn.recv()
                kind = msg[0]
                if kind == "shutdown":
                    engine.shutdown()
                    conn.send(("bye",))
                    return
                if kind == "speed":
                    speed = max(1, min(MAX_SPEED, int(msg[1])))
                    perf.update(speed=speed, displayEvery=display_every(speed))
                    rebase()
                elif kind == "cmd":
                    was_running = engine.running
                    try:
                        engine.command(msg[1], *msg[2])
                    except Exception as e:
                        traceback.print_exc()
                        buf("editResult", {"ok": False, "message": f"{msg[1]} failed: {e}", "picked": None})
                    if engine.running and not was_running or msg[1] in ("reset", "setEditMode"):
                        rebase()
                    flush()
                behind = False

            now = time.perf_counter()
            if now - t_last_jobs >= JOB_POLL_S:
                t_last_jobs = now
                engine.poll_jobs()
                if buf.items:
                    flush()

            if not engine.running:
                continue

            # ── steps due by the wall clock ──────────────────────────────
            due_t = anchor[1] + (now - anchor[0]) * speed
            if engine.sim_time + dt * 0.5 > due_t:
                continue
            t0 = time.perf_counter()
            snap = engine.step()
            step_ms = (time.perf_counter() - t0) * 1e3
            perf["stepMs"] += 0.05 * (step_ms - perf["stepMs"])
            steps_since_frame += 1
            # Running flat out: more than 1 s of sim time behind → drop the backlog
            if due_t - engine.sim_time > max(1.0, speed * 0.5):
                rebase()
            frame_due = steps_since_frame >= display_every(speed) or \
                time.perf_counter() - t_last_frame >= MAX_FRAME_GAP_S
            if frame_due:
                t_now = time.perf_counter()
                eff_window.append((t_now, engine.sim_time))
                while len(eff_window) > 2 and t_now - eff_window[0][0] > 2.0:
                    eff_window.pop(0)
                (w0, s0), (w1, s1) = eff_window[0], eff_window[-1]
                perf["effective"] = round((s1 - s0) / (w1 - w0), 2) if w1 > w0 else 0.0
                engine.publish(snap)
                buf("perfUpdated", dict(perf, stepMs=round(perf["stepMs"], 2),
                                        simPid=os.getpid()))
                flush()
    except (EOFError, BrokenPipeError, KeyboardInterrupt):
        engine.shutdown()
