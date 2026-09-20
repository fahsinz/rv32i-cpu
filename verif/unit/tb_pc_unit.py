"""cocotb testbench for rtl/pc_unit.sv.

Covers reset, sequential fetch, taken and not-taken branches, JAL, JALR
(including the mandatory clearing of bit 0), stall, and the misaligned-target
flag, then replays a long random control sequence against a Python model.
"""

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer

from verif.bits import MASK32, as_int

RESET_PC = 0x0000_0000


def ref_next_pc(pc: int, branch: int, taken: int, jump: int, jalr: int, imm: int, alu: int) -> int:
    if jalr:
        return alu & ~1 & MASK32
    if jump or (branch and taken):
        return (pc + imm) & MASK32
    return (pc + 4) & MASK32


async def setup(dut):
    Clock(dut.clk, 10, unit="ns").start()
    dut.rst.value = 1
    dut.stall.value = 0
    dut.branch.value = 0
    dut.taken.value = 0
    dut.jump.value = 0
    dut.jalr.value = 0
    dut.imm.value = 0
    dut.alu_result.value = 0
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.rst.value = 0


async def drive(dut, branch=0, taken=0, jump=0, jalr=0, imm=0, alu=0):
    """Apply controls, verify combinational outputs, then advance one clock."""
    dut.branch.value = branch
    dut.taken.value = taken
    dut.jump.value = jump
    dut.jalr.value = jalr
    dut.imm.value = imm & MASK32
    dut.alu_result.value = alu & MASK32
    await Timer(1, unit="ns")

    pc = as_int(dut.pc)
    exp_next = ref_next_pc(pc, branch, taken, jump, jalr, imm, alu)
    got_next = as_int(dut.pc_next)
    assert got_next == exp_next, f"pc=0x{pc:08x}: pc_next 0x{got_next:08x}, expected 0x{exp_next:08x}"
    assert as_int(dut.pc_plus4) == (pc + 4) & MASK32, "pc_plus4 wrong"
    assert as_int(dut.misaligned_target) == int(bool(exp_next & 3)), "misaligned_target wrong"

    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    return exp_next


@cocotb.test()
async def pc_reset_and_sequential(dut):
    await setup(dut)
    await Timer(1, unit="ns")
    assert as_int(dut.pc) == RESET_PC, f"reset PC is 0x{as_int(dut.pc):08x}"
    for step in range(20):
        await drive(dut)
        await Timer(1, unit="ns")
        assert as_int(dut.pc) == RESET_PC + 4 * (step + 1), "PC did not advance by 4"


@cocotb.test()
async def pc_branches_and_jumps(dut):
    await setup(dut)
    await drive(dut, branch=1, taken=0, imm=0x100)      # not taken: falls through
    await Timer(1, unit="ns")
    assert as_int(dut.pc) == 4

    await drive(dut, branch=1, taken=1, imm=0x40)       # taken: pc + imm
    await Timer(1, unit="ns")
    assert as_int(dut.pc) == 0x44

    await drive(dut, branch=1, taken=1, imm=(-0x40) & MASK32)  # backward branch
    await Timer(1, unit="ns")
    assert as_int(dut.pc) == 0x04

    await drive(dut, jump=1, imm=0x200)                 # JAL
    await Timer(1, unit="ns")
    assert as_int(dut.pc) == 0x204

    await drive(dut, jalr=1, alu=0x1001)                # JALR clears bit 0
    await Timer(1, unit="ns")
    assert as_int(dut.pc) == 0x1000, f"JALR did not clear bit 0: 0x{as_int(dut.pc):08x}"


@cocotb.test()
async def pc_stall_holds(dut):
    await setup(dut)
    await drive(dut)
    await Timer(1, unit="ns")
    held = as_int(dut.pc)
    dut.stall.value = 1
    for _ in range(5):
        await RisingEdge(dut.clk)
        await FallingEdge(dut.clk)
        await Timer(1, unit="ns")
        assert as_int(dut.pc) == held, "PC moved while stalled"
    dut.stall.value = 0
    await drive(dut)
    await Timer(1, unit="ns")
    assert as_int(dut.pc) == held + 4, "PC did not resume after stall"


@cocotb.test()
async def pc_misaligned_target(dut):
    await setup(dut)
    # A branch immediate always has bit 0 clear, but bit 1 can be set.
    dut.branch.value = 1
    dut.taken.value = 1
    dut.imm.value = 0x2
    await Timer(1, unit="ns")
    assert as_int(dut.misaligned_target) == 1, "2-byte aligned target not flagged"
    dut.imm.value = 0x4
    await Timer(1, unit="ns")
    assert as_int(dut.misaligned_target) == 0, "aligned target wrongly flagged"


@cocotb.test()
async def pc_random_sequence(dut):
    await setup(dut)
    for _ in range(2000):
        kind = random.randrange(4)
        await drive(
            dut,
            branch=int(kind == 0),
            taken=random.randrange(2),
            jump=int(kind == 1),
            jalr=int(kind == 2),
            imm=random.choice([0x4, 0x40, (-0x40) & MASK32, random.getrandbits(32) & ~1]),
            alu=random.getrandbits(32),
        )
