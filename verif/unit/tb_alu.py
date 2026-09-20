"""cocotb testbench for rtl/alu.sv.

Every operation is checked against an independent Python reference, first on a
cross product of corner values (sign boundaries, shift boundaries, alternating
bit patterns) and then on random operands.
"""

import random

import cocotb
from cocotb.triggers import Timer

from verif.bits import MASK32, to_signed
from verif.isa import ALU_OPS

REFERENCE = {
    "ADD": lambda a, b: (a + b) & MASK32,
    "SUB": lambda a, b: (a - b) & MASK32,
    "SLL": lambda a, b: (a << (b & 0x1F)) & MASK32,
    "SLT": lambda a, b: int(to_signed(a) < to_signed(b)),
    "SLTU": lambda a, b: int(a < b),
    "XOR": lambda a, b: a ^ b,
    "SRL": lambda a, b: a >> (b & 0x1F),
    "SRA": lambda a, b: (to_signed(a) >> (b & 0x1F)) & MASK32,
    "OR": lambda a, b: a | b,
    "AND": lambda a, b: a & b,
}

CORNERS = [
    0x0000_0000, 0x0000_0001, 0x0000_0002, 0x0000_001F, 0x0000_0020,
    0x7FFF_FFFF, 0x8000_0000, 0x8000_0001, 0xFFFF_FFFE, 0xFFFF_FFFF,
    0x5555_5555, 0xAAAA_AAAA,
]


async def check(dut, op: str, a: int, b: int) -> None:
    dut.op.value = ALU_OPS[op]
    dut.a.value = a
    dut.b.value = b
    await Timer(1, unit="ns")
    got = dut.y.value.to_unsigned()
    exp = REFERENCE[op](a, b)
    assert got == exp, f"{op} a=0x{a:08x} b=0x{b:08x}: got 0x{got:08x}, expected 0x{exp:08x}"


@cocotb.test()
async def alu_corner_cases(dut):
    for op in ALU_OPS:
        for a in CORNERS:
            for b in CORNERS:
                await check(dut, op, a, b)


@cocotb.test()
async def alu_random(dut):
    for _ in range(5000):
        op = random.choice(list(ALU_OPS))
        await check(dut, op, random.getrandbits(32), random.getrandbits(32))


@cocotb.test()
async def alu_undefined_op_is_zero(dut):
    for op in set(range(16)) - set(ALU_OPS.values()):
        dut.op.value = op
        dut.a.value = 0xDEAD_BEEF
        dut.b.value = 0x1234_5678
        await Timer(1, unit="ns")
        assert dut.y.value.to_unsigned() == 0, f"op=0b{op:04b} should output 0"
