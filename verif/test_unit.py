"""pytest entry point for block-level tests: one simulator build + cocotb run per RTL module."""

import pytest

from verif.sim import run_cocotb

UNITS = [
    # toplevel      RTL sources        cocotb testbench          parameters
    ("alu",        ["alu.sv"],        "verif.unit.tb_alu",        {}),
    ("regfile",    ["regfile.sv"],    "verif.unit.tb_regfile",    {}),
    ("imm_gen",    ["imm_gen.sv"],    "verif.unit.tb_imm_gen",    {}),
    ("decoder",    ["decoder.sv"],    "verif.unit.tb_decoder",    {}),
    ("branch_cmp", ["branch_cmp.sv"], "verif.unit.tb_branch_cmp", {}),
    # A small array keeps the build quick and lets random addresses wrap.
    ("memory",     ["memory.sv"],     "verif.unit.tb_memory",     {"WORDS": 256}),
    ("pc_unit",    ["pc_unit.sv"],    "verif.unit.tb_pc_unit",    {}),
]


@pytest.mark.parametrize("toplevel, rtl_files, tb, parameters", UNITS, ids=[u[0] for u in UNITS])
def test_unit(toplevel, rtl_files, tb, parameters):
    run_cocotb(toplevel, rtl_files, tb, parameters=parameters)
