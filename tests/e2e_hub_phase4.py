"""
End-to-end check of the Phase 4 behavior through the real hub: starts the Hub class from GSE_Unified_Software
in-process on a side port, runs main.py as a subprocess (mock mode, config/demo_local) as a spoke, and sends
commands the way the hub UI would.

Not a pytest test (needs the unified repo and spawns main.py), so the name has no test_ prefix.

Usage (from the launch_controller folder, with src/settings.py MOCK_MODE = True):
    .venv/bin/python tests/e2e_hub_phase4.py
    GSE_REPO=/path/to/GSE_Unified_Software .venv/bin/python tests/e2e_hub_phase4.py

Checks: last-step telemetry keys, InvalidValveStateError prefix (exactly once) + force, invalid step rejected,
StepSequenceError on a wrong expected_last_step and a run on the right one, safe_system during a step returns
at once and aborts it, a second safe gets BusyError, and last_successful_* is unchanged by the abort.

Starting point for the Phase 5 checks still to do: a step that is running when the hub dies finishes, and
telemetry shows it after the reconnect; fill + prop connected at once.
Exit code: 0 if every check passes, 1 otherwise.
"""
import asyncio
import os
import subprocess
import sys
import time

LC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GSE = os.environ.get("GSE_REPO", os.path.join(os.path.dirname(LC), "GSE_Unified_Software"))
if not os.path.isfile(os.path.join(GSE, "hub.py")):
    sys.exit(f"hub.py not found in {GSE}; set GSE_REPO to the GSE_Unified_Software folder")

# Import the hub from the unified repo (its generated/ stubs match ours, but load its copy).
sys.path.insert(0, GSE)
sys.path.insert(0, os.path.join(GSE, "generated"))
import grpc
from hub import Hub, KEEPALIVE_OPTIONS
from generated import controller_pb2, controller_pb2_grpc

ADDR = "localhost:50777"  # side port, so a hub on 50051 isn't disturbed
NODE = "e2e_lc"
CONFIG = "config/demo_local"

ok = True


def check(cond, label, extra=""):
    global ok
    ok &= bool(cond)
    print(("PASS " if cond else "FAIL ") + label + (f"  [{extra}]" if extra else ""))


def succeeded(response) -> bool:
    return response.status == controller_pb2.COMPLETED


async def main() -> None:
    hub = Hub()
    server = grpc.aio.server(options=KEEPALIVE_OPTIONS)
    controller_pb2_grpc.add_ControllerServicer_to_server(hub, server)
    server.add_insecure_port(ADDR)
    await server.start()
    proc = subprocess.Popen(
        [sys.executable, "main.py", "-c", f"{CONFIG}/controller_config.json", "-w", f"{CONFIG}/website_config.json",
         "--node_id", NODE, "--hub_addr", ADDR],
        cwd=LC, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(100):
            if NODE in hub.sessions and NODE in hub.latest:
                break
            await asyncio.sleep(0.1)
        check(NODE in hub.sessions, "spoke connected")
        if NODE not in hub.sessions:
            return

        def send(name, **args):
            return hub.send(NODE, name, {k: str(v) for k, v in args.items()})

        def telemetry():
            return hub.latest[NODE]["values"]

        t = telemetry()
        check(t["last_step_result"] == "none" and t["last_successful_step_index"] == -1,
              "telemetry has last_step keys (none yet)")

        # --- Invalid valve states (demo rule: valves 1 and 2 not both open) ---
        await send("set_valves", **{"1": "closed", "2": "closed"})
        r = await send("set_valve", valve_id=1, state="open")
        check(succeeded(r), "set valve 1 open")
        r = await send("set_valve", valve_id=2, state="open")
        check(not succeeded(r) and r.message.startswith("InvalidValveStateError: ")
              and r.message.count("InvalidValveStateError") == 1,
              "invalid change rejected with prefix once", r.message)
        r = await send("set_valve", valve_id=2, state="open", force="true")
        check(succeeded(r), "forced change accepted")
        await send("set_valves", **{"1": "closed", "2": "closed"})

        r = await send("start_step", procedure_index=0, step_index=0)  # opens 1, then 2
        check(not succeeded(r) and r.message.startswith("InvalidValveStateError:"), "invalid step rejected", r.message[:60])

        # --- Step sequence ---
        r = await send("start_step", procedure_index=0, step_index=2, expected_last_step="0:1")
        check(not succeeded(r) and r.message == "StepSequenceError: last successful step is none", "sequence mismatch", r.message)
        r = await send("start_step", procedure_index=0, step_index=2, expected_last_step="none")  # 0.5 s pulse
        check(succeeded(r), "sequence match runs step")
        await asyncio.sleep(1.0)
        t = telemetry()
        check(t["last_step_result"] == "completed" and t["last_successful_procedure_index"] == 0
              and t["last_successful_step_index"] == 2, "telemetry shows last successful step 0:2")

        # --- Safe during a step aborts it: procedure 1 step 0 (open 1, wait 5 s, ...) ---
        r = await send("start_step", procedure_index=1, step_index=0, force="true")
        check(succeeded(r), "start long step")
        await asyncio.sleep(0.5)
        started = time.time()
        r = await send("safe_system", operator="e2e")
        check(succeeded(r) and time.time() - started < 0.5, "safe_system during step returns at once")
        r = await send("safe_system")
        check(not succeeded(r) and r.message.startswith("BusyError: System is already being safed"), "second safe rejected", r.message)
        await asyncio.sleep(0.4)
        t = telemetry()
        check(t["last_step_result"] == "aborted" and t["last_step_procedure_index"] == 1
              and not t["proc_1_step_0_done"], "telemetry shows step aborted")
        check(t["last_successful_step_index"] == 2, "last successful step unchanged by abort")
    finally:
        proc.terminate()
        proc.wait(5)
        await server.stop(0)


if __name__ == "__main__":
    asyncio.run(main())
    print("ALL PASS" if ok else "SOME FAILED")
    sys.exit(0 if ok else 1)
