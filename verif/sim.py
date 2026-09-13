"""Build-and-run helper around the cocotb Python runner.

Environment knobs:
  SIM=icarus               simulator passed to cocotb (default: icarus)
  WAVES=1                  dump waveforms into sim_build/<toplevel>/
  COCOTB_RANDOM_SEED=<n>   reproduce a randomized run (the seed is printed in every log)
"""

import os
import sys
from pathlib import Path

from cocotb_tools.runner import get_runner

REPO_ROOT = Path(__file__).resolve().parents[1]
RTL_DIR = REPO_ROOT / "rtl"
BUILD_ROOT = REPO_ROOT / "sim_build"
PACKAGES = [RTL_DIR / "rv32i_pkg.sv"]


def run_cocotb(toplevel: str, rtl_files: list[str], test_module: str, parameters: dict | None = None) -> None:
    """Compile rv32i_pkg.sv plus `rtl_files`, then run every cocotb test in `test_module`."""
    sim = os.environ.get("SIM", "icarus")
    waves = os.environ.get("WAVES") == "1"
    build_dir = BUILD_ROOT / toplevel

    # The simulator's embedded Python inherits sys.path, so `verif.*` imports must resolve from here.
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

    runner = get_runner(sim)
    runner.build(
        sources=PACKAGES + [RTL_DIR / f for f in rtl_files],
        hdl_toplevel=toplevel,
        parameters=parameters or {},
        build_dir=build_dir,
        timescale=("1ns", "1ps"),
        waves=waves,
        always=True,
    )
    # Under pytest, runner.test() parses the results file itself and fails the test on any cocotb failure.
    runner.test(
        hdl_toplevel=toplevel,
        test_module=test_module,
        build_dir=build_dir,
        test_dir=build_dir,
        waves=waves,
    )
