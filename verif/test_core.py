"""pytest entry point for the full-core scoreboard run."""

from verif.sim import run_cocotb

RTL = [
    "alu.sv", "regfile.sv", "imm_gen.sv", "decoder.sv",
    "branch_cmp.sv", "memory.sv", "pc_unit.sv", "core.sv", "soc.sv",
]


def test_core():
    # WORDS must match verif/tb_core.py.
    run_cocotb("soc", RTL, "verif.tb_core", parameters={"WORDS": 1024})
