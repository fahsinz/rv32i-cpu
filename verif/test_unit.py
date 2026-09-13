"""pytest entry point for block-level tests: one simulator build + cocotb run per RTL module."""

import pytest

from verif.sim import run_cocotb

UNITS = [
    # toplevel   RTL sources      cocotb testbench
    ("alu",     ["alu.sv"],     "verif.unit.tb_alu"),
    ("regfile", ["regfile.sv"], "verif.unit.tb_regfile"),
    ("imm_gen", ["imm_gen.sv"], "verif.unit.tb_imm_gen"),
]


@pytest.mark.parametrize("toplevel, rtl_files, tb", UNITS, ids=[u[0] for u in UNITS])
def test_unit(toplevel, rtl_files, tb):
    run_cocotb(toplevel, rtl_files, tb)
