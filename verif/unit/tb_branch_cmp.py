"""cocotb testbench for rtl/branch_cmp.sv.

The interesting failures here are signed/unsigned mix-ups, so the corner list
pairs values that compare one way as signed and the other way as unsigned.
"""

import random

import cocotb
from cocotb.triggers import Timer

from verif.bits import as_int, to_signed

BRANCHES = {"BEQ": 0b000, "BNE": 0b001, "BLT": 0b100, "BGE": 0b101, "BLTU": 0b110, "BGEU": 0b111}

REFERENCE = {
    "BEQ": lambda a, b: a == b,
    "BNE": lambda a, b: a != b,
    "BLT": lambda a, b: to_signed(a) < to_signed(b),
    "BGE": lambda a, b: to_signed(a) >= to_signed(b),
    "BLTU": lambda a, b: a < b,
    "BGEU": lambda a, b: a >= b,
}

CORNERS = [0x0000_0000, 0x0000_0001, 0x7FFF_FFFF, 0x8000_0000, 0x8000_0001, 0xFFFF_FFFF]


async def check(dut, name: str, a: int, b: int) -> None:
    dut.a.value = a
    dut.b.value = b
    dut.funct3.value = BRANCHES[name]
    await Timer(1, unit="ns")
    got = as_int(dut.taken)
    exp = int(REFERENCE[name](a, b))
    assert got == exp, f"{name} a=0x{a:08x} b=0x{b:08x}: got {got}, expected {exp}"


@cocotb.test()
async def branch_corner_cases(dut):
    for name in BRANCHES:
        for a in CORNERS:
            for b in CORNERS:
                await check(dut, name, a, b)


@cocotb.test()
async def branch_random(dut):
    for _ in range(4000):
        name = random.choice(list(BRANCHES))
        a = random.getrandbits(32)
        # Half the time compare against an equal or near-equal value, so BEQ/BGE
        # see the boundary instead of only random inequality.
        b = random.choice([a, (a + 1) & 0xFFFF_FFFF, (a - 1) & 0xFFFF_FFFF, random.getrandbits(32)])
        await check(dut, name, a, b)


@cocotb.test()
async def branch_unused_funct3_never_taken(dut):
    """funct3 010 and 011 are not RV32I branches and must never be taken."""
    for funct3 in (0b010, 0b011):
        for a, b in ((0, 0), (5, 5), (0xFFFF_FFFF, 0)):
            dut.a.value = a
            dut.b.value = b
            dut.funct3.value = funct3
            await Timer(1, unit="ns")
            assert as_int(dut.taken) == 0, f"funct3=0b{funct3:03b} must not branch"
