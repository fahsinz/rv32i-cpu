"""cocotb testbench for rtl/imm_gen.sv.

The reference rebuilds each immediate from the field layout in the RISC-V spec.
A walking-one sweep over all 32 instruction bits pins down every wire in the
bit-scramble individually, so a single swapped bit can't hide.
"""

import random

import cocotb
from cocotb.triggers import Timer

from verif.bits import bits, sign_extend

# Mirrors rv32i_pkg.sv
IMM_SEL = {"I": 0, "S": 1, "B": 2, "U": 3, "J": 4}


def ref_imm(fmt: str, inst: int) -> int:
    if fmt == "I":
        return sign_extend(bits(inst, 31, 20), 12)
    if fmt == "S":
        return sign_extend(bits(inst, 31, 25) << 5 | bits(inst, 11, 7), 12)
    if fmt == "B":
        raw = bits(inst, 31, 31) << 12 | bits(inst, 7, 7) << 11 | bits(inst, 30, 25) << 5 | bits(inst, 11, 8) << 1
        return sign_extend(raw, 13)
    if fmt == "U":
        return bits(inst, 31, 12) << 12
    if fmt == "J":
        raw = bits(inst, 31, 31) << 20 | bits(inst, 19, 12) << 12 | bits(inst, 20, 20) << 11 | bits(inst, 30, 21) << 1
        return sign_extend(raw, 21)
    raise ValueError(fmt)


async def check(dut, fmt: str, inst: int) -> None:
    dut.inst.value = inst
    dut.imm_sel.value = IMM_SEL[fmt]
    await Timer(1, unit="ns")
    got = dut.imm.value.to_unsigned()
    exp = ref_imm(fmt, inst)
    assert got == exp, f"{fmt}-type inst=0x{inst:08x}: got 0x{got:08x}, expected 0x{exp:08x}"


@cocotb.test()
async def imm_walking_ones(dut):
    for fmt in IMM_SEL:
        for bit in range(32):
            await check(dut, fmt, 1 << bit)
            await check(dut, fmt, ~(1 << bit) & 0xFFFF_FFFF)


@cocotb.test()
async def imm_extremes(dut):
    for fmt in IMM_SEL:
        for inst in (0x0000_0000, 0xFFFF_FFFF, 0x8000_0000, 0x7FFF_FFFF):
            await check(dut, fmt, inst)


@cocotb.test()
async def imm_random(dut):
    for _ in range(4000):
        await check(dut, random.choice(list(IMM_SEL)), random.getrandbits(32))
