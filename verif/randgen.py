"""Constrained-random program generator.

The constraints exist so random programs stay interesting instead of trapping
on their first instruction:

* x31 is reserved as a data pointer, set once at the top and never written, so
  loads and stores hit a known data region.
* Memory offsets are aligned to the access width, so programs do not all halt
  on a misaligned access. (A directed test covers misalignment on purpose.)
* Branch and jump targets land on 4-byte boundaries inside the program, so
  control flow stays in bounds. Loops are allowed: the comparison runs for a
  bounded number of instructions, so a program that never halts is still useful.
* No ECALL/EBREAK except the one at the end, so programs run for a while.
"""

import random

from verif import isa

DATA_BASE = 0x400  # byte address of the random data region
DATA_SIZE = 0x100

SAFE_REGS = list(range(1, 31))  # x31 is the data pointer, x0 is special but legal as an operand
ALU_IMM_F3 = [0b000, 0b010, 0b011, 0b100, 0b110, 0b111]
LOAD_F3 = {0b000: 1, 0b001: 2, 0b010: 4, 0b100: 1, 0b101: 2}  # funct3 -> alignment
STORE_F3 = {0b000: 1, 0b001: 2, 0b010: 4}
BRANCH_F3 = [0b000, 0b001, 0b100, 0b101, 0b110, 0b111]


def _aligned_offset(align: int) -> int:
    return random.randrange(0, DATA_SIZE, align) if align > 1 else random.randrange(DATA_SIZE)


def random_program(length: int = 60) -> list[int]:
    """Build a random but well-behaved program, ending in ECALL."""
    body_len = max(1, length - 3)
    words: list[int] = []

    # Prologue: x31 = DATA_BASE (two instructions, so body starts at byte 8).
    words.append(isa.u_type((DATA_BASE + 0x800) >> 12, 31, isa.OP_LUI))
    words.append(isa.i_type(DATA_BASE - (((DATA_BASE + 0x800) >> 12) << 12), 31, 0b000, 31, isa.OP_IMM))
    prologue = len(words)

    for index in range(body_len):
        pc = (prologue + index) * 4
        rd = random.choice(SAFE_REGS)
        rs1, rs2 = random.choice(SAFE_REGS + [0]), random.choice(SAFE_REGS + [0])
        kind = random.choices(
            ["alu_imm", "alu_reg", "shift", "load", "store", "branch", "lui", "auipc", "jal"],
            weights=[22, 22, 10, 12, 12, 14, 3, 3, 2],
        )[0]

        if kind == "alu_imm":
            words.append(isa.i_type(random.getrandbits(12), rs1, random.choice(ALU_IMM_F3), rd, isa.OP_IMM))
        elif kind == "alu_reg":
            funct3 = random.randrange(8)
            funct7 = random.choice([0x00, 0x20]) if funct3 in (0b000, 0b101) else 0x00
            words.append(isa.r_type(funct7, rs2, rs1, funct3, rd, isa.OP_REG))
        elif kind == "shift":
            funct3 = random.choice([0b001, 0b101])
            funct7 = random.choice([0x00, 0x20]) if funct3 == 0b101 else 0x00
            shamt = random.choice([0, 1, 31, random.randrange(32)])
            words.append(isa.i_type((funct7 << 5) | shamt, rs1, funct3, rd, isa.OP_IMM))
        elif kind == "load":
            funct3 = random.choice(list(LOAD_F3))
            words.append(isa.i_type(_aligned_offset(LOAD_F3[funct3]), 31, funct3, rd, isa.OP_LOAD))
        elif kind == "store":
            funct3 = random.choice(list(STORE_F3))
            words.append(isa.s_type(_aligned_offset(STORE_F3[funct3]), rs2, 31, funct3, isa.OP_STORE))
        elif kind == "branch":
            # Target a 4-byte boundary inside the program.
            target = random.randrange(prologue * 4, (prologue + body_len) * 4, 4)
            words.append(isa.b_type(target - pc, rs2, rs1, random.choice(BRANCH_F3), isa.OP_BRANCH))
        elif kind == "lui":
            words.append(isa.u_type(random.getrandbits(20), rd, isa.OP_LUI))
        elif kind == "auipc":
            words.append(isa.u_type(random.getrandbits(20), rd, isa.OP_AUIPC))
        else:  # jal, forward only so it cannot spin on itself
            target = random.randrange(pc + 4, (prologue + body_len) * 4 + 4, 4)
            words.append(isa.j_type(target - pc, rd, isa.OP_JAL))

    words.append(0x0000_0073)  # ecall
    return words


def demo() -> None:
    """Self-check: generated programs run a while in the model without trapping early."""
    from verif.iss import HALT_ECALL, Iss

    random.seed(7)
    total = 0
    for _ in range(20):
        program = random_program(60)
        iss = Iss(program, words=1024)
        trace = iss.run(400)
        total += len(trace)
        # The property that matters: it ran out of budget (a loop) or reached the
        # final ECALL, never an illegal instruction or a misaligned access.
        assert iss.halt_cause in (0, HALT_ECALL), f"halt cause {iss.halt_cause}"
    assert total > 20 * 20, f"programs are too short on average: {total / 20:.1f}"
    print(f"randgen demo OK ({total / 20:.0f} instructions per program on average)")


if __name__ == "__main__":
    demo()
