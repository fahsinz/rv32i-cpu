"""Functional coverage for the core.

Bins are sampled from retired instructions, so coverage reflects what the core
actually executed rather than what the stimulus intended. `missing()` is what
turns coverage into a pass/fail signal instead of a report nobody reads.
"""

from collections import Counter

from verif.bits import bits, to_signed

OPCODE_NAMES = {
    0b0110111: "lui", 0b0010111: "auipc", 0b1101111: "jal", 0b1100111: "jalr",
    0b1100011: "branch", 0b0000011: "load", 0b0100011: "store",
    0b0010011: "op-imm", 0b0110011: "op-reg", 0b0001111: "fence", 0b1110011: "system",
}
BRANCH_NAMES = {0b000: "beq", 0b001: "bne", 0b100: "blt", 0b101: "bge", 0b110: "bltu", 0b111: "bgeu"}
LOAD_NAMES = {0b000: "lb", 0b001: "lh", 0b010: "lw", 0b100: "lbu", 0b101: "lhu"}
STORE_NAMES = {0b000: "sb", 0b001: "sh", 0b010: "sw"}
ALU_IMM_NAMES = {0b000: "addi", 0b010: "slti", 0b011: "sltiu", 0b100: "xori",
                 0b110: "ori", 0b111: "andi", 0b001: "slli", 0b101: "srli/srai"}
ALU_REG_NAMES = {0b000: "add/sub", 0b001: "sll", 0b010: "slt", 0b011: "sltu",
                 0b100: "xor", 0b101: "srl/sra", 0b110: "or", 0b111: "and"}

# Bins that a complete regression must hit at least once.
REQUIRED = [
    # every instruction group
    "op:lui", "op:auipc", "op:jal", "op:jalr", "op:branch", "op:load",
    "op:store", "op:op-imm", "op:op-reg",
    # every branch kind, both outcomes
    *[f"branch:{n}" for n in BRANCH_NAMES.values()],
    "branch:taken", "branch:not-taken",
    # every memory width
    *[f"mem:{n}" for n in LOAD_NAMES.values()],
    *[f"mem:{n}" for n in STORE_NAMES.values()],
    # arithmetic corners
    "shift:zero", "shift:max", "result:zero", "result:negative",
    "rd:x0", "rs1:x0",
    # sub-word access to a non-zero byte lane
    "mem:unaligned-lane",
]


def sample(counts: Counter, inst: int, commit) -> None:
    """Record coverage for one retired instruction."""
    opcode = bits(inst, 6, 0)
    funct3, funct7 = bits(inst, 14, 12), bits(inst, 31, 25)
    name = OPCODE_NAMES.get(opcode)
    if name is None:
        counts["op:unknown"] += 1
        return
    counts[f"op:{name}"] += 1

    if bits(inst, 11, 7) == 0 and commit.rd == 0 and name in ("op-imm", "op-reg", "lui"):
        counts["rd:x0"] += 1
    if bits(inst, 19, 15) == 0:
        counts["rs1:x0"] += 1

    if name == "branch":
        counts[f"branch:{BRANCH_NAMES.get(funct3, funct3)}"] += 1
        counts["branch:taken" if commit.next_pc != (commit.pc + 4) & 0xFFFF_FFFF
               else "branch:not-taken"] += 1
    elif name == "load":
        counts[f"mem:{LOAD_NAMES.get(funct3, funct3)}"] += 1
        if commit.mem_addr & 3:
            counts["mem:unaligned-lane"] += 1
    elif name == "store":
        counts[f"mem:{STORE_NAMES.get(funct3, funct3)}"] += 1
        if commit.mem_addr & 3:
            counts["mem:unaligned-lane"] += 1
    elif name == "op-imm":
        counts[f"alu:{ALU_IMM_NAMES.get(funct3, funct3)}"] += 1
        if funct3 in (0b001, 0b101):
            shamt = bits(inst, 24, 20)
            if shamt == 0:
                counts["shift:zero"] += 1
            if shamt == 31:
                counts["shift:max"] += 1
    elif name == "op-reg":
        counts[f"alu:{ALU_REG_NAMES.get(funct3, funct3)}"] += 1
        if funct7 == 0x20:
            counts["alu:alt-funct7"] += 1

    if commit.rd != 0:
        if commit.rd_wdata == 0:
            counts["result:zero"] += 1
        if to_signed(commit.rd_wdata) < 0:
            counts["result:negative"] += 1


def missing(counts: Counter) -> list[str]:
    return [b for b in REQUIRED if counts[b] == 0]


def report(counts: Counter) -> str:
    lines = [f"{'bin':<28} {'hits':>8}"]
    for name in sorted(counts):
        lines.append(f"{name:<28} {counts[name]:>8}")
    gaps = missing(counts)
    lines.append("")
    lines.append(f"required bins hit: {len(REQUIRED) - len(gaps)}/{len(REQUIRED)}")
    if gaps:
        lines.append("MISSING: " + ", ".join(gaps))
    return "\n".join(lines)
