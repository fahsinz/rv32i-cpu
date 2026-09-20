"""cocotb testbench for rtl/decoder.sv.

Three angles: hand-written encodings of real instructions, randomly built legal
instructions covering every opcode and legal funct3/funct7, and fully random
32-bit words, most of which are illegal and must produce no side effects.
"""

import random

import cocotb
from cocotb.triggers import Timer

from verif import isa
from verif.bits import as_int, bits

PORTS = (
    "alu_op", "alu_a_sel", "alu_b_sel", "imm_sel", "reg_write", "wb_sel",
    "mem_read", "mem_write", "mem_op", "branch", "jump", "jalr",
    "ecall", "ebreak", "illegal",
)


def ref_decode(inst: int) -> dict:
    opcode, funct3, funct7 = bits(inst, 6, 0), bits(inst, 14, 12), bits(inst, 31, 25)
    c = dict(
        alu_op=isa.ALU_OPS["ADD"], alu_a_sel=isa.ALU_A_RS1, alu_b_sel=isa.ALU_B_IMM,
        imm_sel=isa.IMM_SEL["I"], reg_write=0, wb_sel=isa.WB_ALU, mem_read=0,
        mem_write=0, mem_op=funct3, branch=0, jump=0, jalr=0, ecall=0, ebreak=0, illegal=0,
    )

    if opcode == isa.OP_LUI:
        c.update(alu_a_sel=isa.ALU_A_ZERO, imm_sel=isa.IMM_SEL["U"], reg_write=1)
    elif opcode == isa.OP_AUIPC:
        c.update(alu_a_sel=isa.ALU_A_PC, imm_sel=isa.IMM_SEL["U"], reg_write=1)
    elif opcode == isa.OP_JAL:
        c.update(imm_sel=isa.IMM_SEL["J"], reg_write=1, wb_sel=isa.WB_PC4, jump=1)
    elif opcode == isa.OP_JALR:
        if funct3 != 0:
            c["illegal"] = 1
        else:
            c.update(reg_write=1, wb_sel=isa.WB_PC4, jalr=1)
    elif opcode == isa.OP_BRANCH:
        c["imm_sel"] = isa.IMM_SEL["B"]
        if funct3 in (0b010, 0b011):
            c["illegal"] = 1
        else:
            c["branch"] = 1
    elif opcode == isa.OP_LOAD:
        if funct3 in (0b011, 0b110, 0b111):
            c["illegal"] = 1
        else:
            c.update(reg_write=1, wb_sel=isa.WB_MEM, mem_read=1)
    elif opcode == isa.OP_STORE:
        c["imm_sel"] = isa.IMM_SEL["S"]
        if funct3 > 0b010:
            c["illegal"] = 1
        else:
            c["mem_write"] = 1
    elif opcode == isa.OP_IMM:
        c.update(reg_write=1, alu_op=(((funct7 >> 5) & 1) << 3 | funct3) if funct3 == 0b101 else funct3)
        if funct3 == 0b001 and funct7 != 0x00:
            c["illegal"] = 1
        if funct3 == 0b101 and funct7 not in (0x00, 0x20):
            c["illegal"] = 1
    elif opcode == isa.OP_REG:
        c.update(alu_b_sel=isa.ALU_B_RS2, reg_write=1, alu_op=((funct7 >> 5) & 1) << 3 | funct3)
        if funct7 != 0x00 and not (funct7 == 0x20 and funct3 in (0b000, 0b101)):
            c["illegal"] = 1
    elif opcode == isa.OP_MISC_MEM:
        if funct3 != 0:
            c["illegal"] = 1
    elif opcode == isa.OP_SYSTEM:
        if bits(inst, 31, 7) == 0:
            c["ecall"] = 1
        elif bits(inst, 31, 20) == 0x001 and bits(inst, 19, 7) == 0:
            c["ebreak"] = 1
        else:
            c["illegal"] = 1
    else:
        c["illegal"] = 1

    if c["illegal"]:
        c.update(reg_write=0, mem_read=0, mem_write=0, branch=0, jump=0, jalr=0, ecall=0, ebreak=0)
    return c


async def check(dut, inst: int, note: str = "") -> None:
    dut.inst.value = inst
    await Timer(1, unit="ns")
    exp = ref_decode(inst)
    got = {p: as_int(getattr(dut, p)) for p in PORTS}
    bad = [f"{p}: got {got[p]}, expected {exp[p]}" for p in PORTS if got[p] != exp[p]]
    assert not bad, f"inst=0x{inst:08x} {note}\n  " + "\n  ".join(bad)


DIRECTED = [
    (0x00100093, "addi x1, x0, 1"),
    (0x123450B7, "lui x1, 0x12345"),
    (0x00000097, "auipc x1, 0"),
    (0x008000EF, "jal x1, 8"),
    (0x000080E7, "jalr x1, 0(x1)"),
    (0xFE000EE3, "beq x0, x0, -4"),
    (0x00052083, "lw x1, 0(x10)"),
    (0xFE512C23, "sw x5, -8(x2)"),
    (0x40208133, "sub x2, x1, x2"),
    (0x4020D133, "sra x2, x1, x2"),
    (0x00509093, "slli x1, x1, 5"),
    (0x40D0D093, "srai x1, x1, 13"),
    (0x0000000F, "fence"),
    (0x00000073, "ecall"),
    (0x00100073, "ebreak"),
    (0x00000000, "all zeros: illegal"),
    (0xFFFFFFFF, "all ones: illegal"),
    (0x00200073, "system with bad funct12: illegal"),
    (0x00000173, "ecall with rd != 0: illegal"),
    (0x0000302F, "unused opcode 0x2F: illegal"),
]


def random_legal() -> int:
    rd, rs1, rs2 = random.randrange(32), random.randrange(32), random.randrange(32)
    imm = random.getrandbits(12)
    kind = random.randrange(9)
    if kind == 0:
        return isa.u_type(random.getrandbits(20), rd, isa.OP_LUI)
    if kind == 1:
        return isa.u_type(random.getrandbits(20), rd, isa.OP_AUIPC)
    if kind == 2:
        return isa.j_type(random.getrandbits(21) & ~1, rd, isa.OP_JAL)
    if kind == 3:
        return isa.i_type(imm, rs1, 0, rd, isa.OP_JALR)
    if kind == 4:
        return isa.b_type(random.getrandbits(13) & ~1, rs2, rs1,
                          random.choice([0, 1, 4, 5, 6, 7]), isa.OP_BRANCH)
    if kind == 5:
        return isa.i_type(imm, rs1, random.choice([0, 1, 2, 4, 5]), rd, isa.OP_LOAD)
    if kind == 6:
        return isa.s_type(imm, rs2, rs1, random.choice([0, 1, 2]), isa.OP_STORE)
    if kind == 7:
        funct3 = random.randrange(8)
        if funct3 == 0b001:
            return isa.i_type(random.randrange(32), rs1, funct3, rd, isa.OP_IMM)
        if funct3 == 0b101:
            return isa.i_type(random.choice([0x000, 0x400]) | random.randrange(32),
                              rs1, funct3, rd, isa.OP_IMM)
        return isa.i_type(imm, rs1, funct3, rd, isa.OP_IMM)
    funct3 = random.randrange(8)
    funct7 = random.choice([0x00, 0x20]) if funct3 in (0b000, 0b101) else 0x00
    return isa.r_type(funct7, rs2, rs1, funct3, rd, isa.OP_REG)


@cocotb.test()
async def decoder_directed(dut):
    for inst, note in DIRECTED:
        await check(dut, inst, note)


@cocotb.test()
async def decoder_random_legal(dut):
    for _ in range(3000):
        await check(dut, random_legal(), "random legal")


@cocotb.test()
async def decoder_random_words(dut):
    """Mostly illegal encodings: none may write a register or memory."""
    for _ in range(5000):
        await check(dut, random.getrandbits(32), "random word")


@cocotb.test()
async def decoder_every_opcode(dut):
    """Sweep all 128 opcode values against a fixed instruction body."""
    for opcode in range(128):
        await check(dut, (0x0AB << 20) | (3 << 15) | (2 << 12) | (4 << 7) | opcode,
                    f"opcode 0x{opcode:02x}")
