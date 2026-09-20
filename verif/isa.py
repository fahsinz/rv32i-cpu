"""RV32I encodings and instruction builders.

The constants mirror rtl/rv32i_pkg.sv. The *_type helpers assemble instruction
words from fields; they are reused by the testbenches, and later by the
assembler and the golden model.
"""

# Opcodes
OP_LUI = 0b0110111
OP_AUIPC = 0b0010111
OP_JAL = 0b1101111
OP_JALR = 0b1100111
OP_BRANCH = 0b1100011
OP_LOAD = 0b0000011
OP_STORE = 0b0100011
OP_IMM = 0b0010011
OP_REG = 0b0110011
OP_MISC_MEM = 0b0001111
OP_SYSTEM = 0b1110011

# ALU operations: {funct7[5], funct3}
ALU_OPS = {
    "ADD": 0b0000,
    "SLL": 0b0001,
    "SLT": 0b0010,
    "SLTU": 0b0011,
    "XOR": 0b0100,
    "SRL": 0b0101,
    "OR": 0b0110,
    "AND": 0b0111,
    "SUB": 0b1000,
    "SRA": 0b1101,
}

# Immediate formats
IMM_SEL = {"I": 0, "S": 1, "B": 2, "U": 3, "J": 4}

# Datapath mux selects
ALU_A_RS1, ALU_A_PC, ALU_A_ZERO = 0, 1, 2
ALU_B_RS2, ALU_B_IMM = 0, 1
WB_ALU, WB_MEM, WB_PC4 = 0, 1, 2


def r_type(funct7: int, rs2: int, rs1: int, funct3: int, rd: int, opcode: int) -> int:
    return (funct7 << 25) | (rs2 << 20) | (rs1 << 15) | (funct3 << 12) | (rd << 7) | opcode


def i_type(imm: int, rs1: int, funct3: int, rd: int, opcode: int) -> int:
    return ((imm & 0xFFF) << 20) | (rs1 << 15) | (funct3 << 12) | (rd << 7) | opcode


def s_type(imm: int, rs2: int, rs1: int, funct3: int, opcode: int) -> int:
    imm &= 0xFFF
    return ((imm >> 5) << 25) | (rs2 << 20) | (rs1 << 15) | (funct3 << 12) | ((imm & 0x1F) << 7) | opcode


def b_type(imm: int, rs2: int, rs1: int, funct3: int, opcode: int) -> int:
    imm &= 0x1FFF  # bit 0 is always zero
    return (
        ((imm >> 12) & 1) << 31 | ((imm >> 5) & 0x3F) << 25 | rs2 << 20 | rs1 << 15
        | funct3 << 12 | ((imm >> 1) & 0xF) << 8 | ((imm >> 11) & 1) << 7 | opcode
    )


def u_type(imm: int, rd: int, opcode: int) -> int:
    return ((imm & 0xFFFFF) << 12) | (rd << 7) | opcode


def j_type(imm: int, rd: int, opcode: int) -> int:
    imm &= 0x1FFFFF  # bit 0 is always zero
    return (
        ((imm >> 20) & 1) << 31 | ((imm >> 1) & 0x3FF) << 21 | ((imm >> 11) & 1) << 20
        | ((imm >> 12) & 0xFF) << 12 | rd << 7 | opcode
    )
