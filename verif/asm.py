"""A small RV32I assembler: assembly text in, 32-bit instruction words out.

Enough of the syntax to write real test programs, and nothing more: labels,
`.word`, comments with # or //, and the handful of pseudo-instructions that make
programs readable (nop, li, mv, j, jr, ret, beqz, bnez).

Keeping this in Python means the test programs live in the repo as text and
need no RISC-V GCC toolchain to build.
"""

import re

from verif import isa

ABI_NAMES = {
    "zero": 0, "ra": 1, "sp": 2, "gp": 3, "tp": 4,
    "t0": 5, "t1": 6, "t2": 7,
    "s0": 8, "fp": 8, "s1": 9,
    "a0": 10, "a1": 11, "a2": 12, "a3": 13, "a4": 14, "a5": 15, "a6": 16, "a7": 17,
    "s2": 18, "s3": 19, "s4": 20, "s5": 21, "s6": 22, "s7": 23, "s8": 24, "s9": 25,
    "s10": 26, "s11": 27,
    "t3": 28, "t4": 29, "t5": 30, "t6": 31,
}

R_TYPE = {
    "add": (0x00, 0b000), "sub": (0x20, 0b000), "sll": (0x00, 0b001),
    "slt": (0x00, 0b010), "sltu": (0x00, 0b011), "xor": (0x00, 0b100),
    "srl": (0x00, 0b101), "sra": (0x20, 0b101), "or": (0x00, 0b110),
    "and": (0x00, 0b111),
}
I_TYPE = {"addi": 0b000, "slti": 0b010, "sltiu": 0b011, "xori": 0b100, "ori": 0b110, "andi": 0b111}
SHIFT_I = {"slli": (0x00, 0b001), "srli": (0x00, 0b101), "srai": (0x20, 0b101)}
LOADS = {"lb": 0b000, "lh": 0b001, "lw": 0b010, "lbu": 0b100, "lhu": 0b101}
STORES = {"sb": 0b000, "sh": 0b001, "sw": 0b010}
BRANCHES = {"beq": 0b000, "bne": 0b001, "blt": 0b100, "bge": 0b101, "bltu": 0b110, "bgeu": 0b111}

OFFSET_RE = re.compile(r"^(-?(?:0x)?[0-9a-fA-F]+)?\s*\(\s*([a-zA-Z0-9]+)\s*\)$")


class AsmError(Exception):
    pass


def _reg(token: str) -> int:
    token = token.strip().lower()
    if token in ABI_NAMES:
        return ABI_NAMES[token]
    if token.startswith("x") and token[1:].isdigit() and 0 <= int(token[1:]) < 32:
        return int(token[1:])
    raise AsmError(f"not a register: {token!r}")


def _imm(token: str, labels: dict, pc: int, relative: bool = False) -> int:
    token = token.strip()
    if token in labels:
        return labels[token] - pc if relative else labels[token]
    try:
        return int(token, 0)
    except ValueError as exc:
        raise AsmError(f"not a number or known label: {token!r}") from exc


def _split_offset(token: str) -> tuple[str, str]:
    """Split `imm(rs1)` into (imm, rs1). A bare register means offset 0."""
    m = OFFSET_RE.match(token.strip())
    if m:
        return (m.group(1) or "0"), m.group(2)
    return "0", token


def _clean(line: str) -> str:
    line = re.split(r"#|//", line, maxsplit=1)[0]
    return line.strip()


def _expand(op: str, args: list[str]) -> list[tuple[str, list[str]]]:
    """Rewrite pseudo-instructions into real ones."""
    if op == "nop":
        return [("addi", ["x0", "x0", "0"])]
    if op == "mv":
        return [("addi", [args[0], args[1], "0"])]
    if op == "j":
        return [("jal", ["x0", args[0]])]
    if op == "jr":
        return [("jalr", ["x0", args[0]])]
    if op == "ret":
        return [("jalr", ["x0", "ra"])]
    if op == "beqz":
        return [("beq", [args[0], "x0", args[1]])]
    if op == "bnez":
        return [("bne", [args[0], "x0", args[1]])]
    if op == "li":
        # Fits in 12 bits: one ADDI. Otherwise LUI + ADDI, with the LUI bumped
        # by one when the low half is negative so the two add up correctly.
        value = int(args[1], 0) & 0xFFFF_FFFF
        low = value & 0xFFF
        if low < 0x800 and (value >> 12) == 0:
            return [("addi", [args[0], "x0", str(value)])]
        if low >= 0x800 and (value >> 12) == 0xFFFFF:
            return [("addi", [args[0], "x0", str(low - 0x1000)])]
        upper = (value + 0x800) >> 12 & 0xFFFFF
        lower = value - (upper << 12)
        lower = ((lower + 0x800) & 0xFFF) - 0x800
        return [("lui", [args[0], str(upper)]), ("addi", [args[0], args[0], str(lower)])]
    return [(op, args)]


def _encode(op: str, args: list[str], pc: int, labels: dict) -> int:
    if op in R_TYPE:
        funct7, funct3 = R_TYPE[op]
        return isa.r_type(funct7, _reg(args[2]), _reg(args[1]), funct3, _reg(args[0]), isa.OP_REG)
    if op in I_TYPE:
        return isa.i_type(_imm(args[2], labels, pc), _reg(args[1]), I_TYPE[op], _reg(args[0]), isa.OP_IMM)
    if op in SHIFT_I:
        funct7, funct3 = SHIFT_I[op]
        shamt = _imm(args[2], labels, pc) & 0x1F
        return isa.i_type((funct7 << 5) | shamt, _reg(args[1]), funct3, _reg(args[0]), isa.OP_IMM)
    if op in LOADS:
        off, base = _split_offset(args[1])
        return isa.i_type(_imm(off, labels, pc), _reg(base), LOADS[op], _reg(args[0]), isa.OP_LOAD)
    if op in STORES:
        off, base = _split_offset(args[1])
        return isa.s_type(_imm(off, labels, pc), _reg(args[0]), _reg(base), STORES[op], isa.OP_STORE)
    if op in BRANCHES:
        target = _imm(args[2], labels, pc, relative=True)
        return isa.b_type(target, _reg(args[1]), _reg(args[0]), BRANCHES[op], isa.OP_BRANCH)
    if op == "lui":
        return isa.u_type(_imm(args[1], labels, pc), _reg(args[0]), isa.OP_LUI)
    if op == "auipc":
        return isa.u_type(_imm(args[1], labels, pc), _reg(args[0]), isa.OP_AUIPC)
    if op == "jal":
        if len(args) == 1:  # jal label  ->  rd = ra
            rd, target = 1, _imm(args[0], labels, pc, relative=True)
        else:
            rd, target = _reg(args[0]), _imm(args[1], labels, pc, relative=True)
        return isa.j_type(target, rd, isa.OP_JAL)
    if op == "jalr":
        if len(args) == 1:  # jalr rs1
            return isa.i_type(0, _reg(args[0]), 0, 1, isa.OP_JALR)
        off, base = _split_offset(args[1])
        return isa.i_type(_imm(off, labels, pc), _reg(base), 0, _reg(args[0]), isa.OP_JALR)
    if op == "ecall":
        return 0x0000_0073
    if op == "ebreak":
        return 0x0010_0073
    if op == "fence":
        return 0x0000_000F
    raise AsmError(f"unknown instruction: {op!r}")


def assemble(text: str, base: int = 0) -> list[int]:
    """Assemble `text` into instruction words, as if loaded at byte address `base`."""
    # Pass 1: find labels, after pseudo-instruction expansion so sizes are known.
    labels: dict[str, int] = {}
    items: list[tuple[int, str, list[str]]] = []
    pc = base
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = _clean(raw)
        while line:
            m = re.match(r"^([A-Za-z_.][A-Za-z0-9_.]*)\s*:\s*(.*)$", line)
            if not m:
                break
            labels[m.group(1)] = pc
            line = m.group(2).strip()
        if not line:
            continue
        head, _, rest = line.partition(" ")
        op = head.strip().lower()
        args = [a.strip() for a in rest.split(",")] if rest.strip() else []
        try:
            if op == ".word":
                for value in args:
                    items.append((pc, ".word", [value]))
                    pc += 4
            else:
                for real_op, real_args in _expand(op, args):
                    items.append((pc, real_op, real_args))
                    pc += 4
        except (AsmError, IndexError, ValueError) as exc:
            raise AsmError(f"line {lineno}: {raw.strip()!r}: {exc}") from exc

    # Pass 2: encode now that every label address is known.
    words = []
    for item_pc, op, args in items:
        try:
            words.append(int(args[0], 0) & 0xFFFF_FFFF if op == ".word"
                         else _encode(op, args, item_pc, labels) & 0xFFFF_FFFF)
        except (AsmError, IndexError, ValueError) as exc:
            raise AsmError(f"at 0x{item_pc:08x} {op} {args}: {exc}") from exc
    return words


def to_hex(words: list[int]) -> str:
    """Render words for $readmemh (one 8-digit word per line)."""
    return "".join(f"{w:08x}\n" for w in words)


def demo() -> None:
    """Self-check: a couple of encodings plus a label round-trip."""
    assert assemble("addi x1, x0, 1") == [0x00100093]
    assert assemble("lw x1, 0(x10)") == [0x00052083]
    assert assemble("sw x5, -8(x2)") == [0xFE512C23]
    assert assemble("sub x2, x1, x2") == [0x40208133]
    assert assemble("srai x1, x1, 13") == [0x40D0D093]
    assert assemble("ecall") == [0x00000073]
    # A backward branch to a label two instructions up: offset -8.
    assert assemble("top: nop\nnop\nbeq x0, x0, top")[2] == 0xFE000CE3
    # li picks one instruction when the value fits, two when it does not.
    assert assemble("li a0, 5") == [0x00500513]
    assert len(assemble("li a0, 0x12345")) == 2
    assert assemble("mv a1, a0") == [0x00050593]
    print("asm demo OK")


if __name__ == "__main__":
    demo()
