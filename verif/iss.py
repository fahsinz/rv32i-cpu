"""Golden model: an RV32I instruction-set simulator written from the spec.

Deliberately independent of the RTL and of the decoder reference used in the
block-level tests. It decodes instructions its own way and reports the same
retirement facts the core exposes on its commit_* port, so the two can be
compared instruction by instruction.

Memory mirrors rtl/memory.sv: word-wide storage, addresses wrapping inside the
array, misaligned halfword/word accesses refused.
"""

from dataclasses import dataclass

from verif.bits import MASK32, bits, sign_extend, to_signed

# Must match the HALT_* constants in rtl/rv32i_pkg.sv
HALT_NONE = 0
HALT_ECALL = 1
HALT_EBREAK = 2
HALT_ILLEGAL = 3
HALT_MEM_MISALIGN = 4
HALT_FETCH_MISALIGN = 5

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


@dataclass
class Commit:
    """What one retired instruction did, matching the core's commit_* port."""

    pc: int
    inst: int
    next_pc: int
    rd: int
    rd_wdata: int
    mem_write: int
    mem_addr: int
    mem_wdata: int


class Trap(Exception):
    def __init__(self, cause: int):
        super().__init__(f"halt cause {cause}")
        self.cause = cause


class Iss:
    def __init__(self, program: list[int], words: int = 4096, reset_pc: int = 0):
        self.words = words
        self.mem = [0] * words
        for i, word in enumerate(program):
            self.mem[i % words] = word & MASK32
        self.regs = [0] * 32
        self.pc = reset_pc & MASK32
        self.halt_cause = HALT_NONE
        self.halted = False

    # ------------------------------------------------------------------ memory
    def _index(self, addr: int) -> int:
        return (addr >> 2) % self.words

    @staticmethod
    def _misaligned(funct3: int, addr: int) -> bool:
        if funct3 in (0b001, 0b101):
            return bool(addr & 1)
        if funct3 == 0b010:
            return bool(addr & 3)
        return False

    def _load(self, funct3: int, addr: int) -> int:
        word = self.mem[self._index(addr)]
        lane_b = (word >> (8 * (addr & 3))) & 0xFF
        lane_h = (word >> 16) & 0xFFFF if addr & 2 else word & 0xFFFF
        if funct3 == 0b000:
            return sign_extend(lane_b, 8)
        if funct3 == 0b001:
            return sign_extend(lane_h, 16)
        if funct3 == 0b100:
            return lane_b
        if funct3 == 0b101:
            return lane_h
        return word

    def _store(self, funct3: int, addr: int, value: int) -> None:
        index = self._index(addr)
        word = self.mem[index]
        if funct3 == 0b000:
            shift = 8 * (addr & 3)
            word = (word & ~(0xFF << shift) & MASK32) | ((value & 0xFF) << shift)
        elif funct3 == 0b001:
            shift = 16 if addr & 2 else 0
            word = (word & ~(0xFFFF << shift) & MASK32) | ((value & 0xFFFF) << shift)
        else:
            word = value & MASK32
        self.mem[index] = word

    # --------------------------------------------------------------- execution
    @staticmethod
    def _alu(funct3: int, funct7_bit5: int, a: int, b: int) -> int:
        shamt = b & 0x1F
        if funct3 == 0b000:
            return (a - b) & MASK32 if funct7_bit5 else (a + b) & MASK32
        if funct3 == 0b001:
            return (a << shamt) & MASK32
        if funct3 == 0b010:
            return int(to_signed(a) < to_signed(b))
        if funct3 == 0b011:
            return int(a < b)
        if funct3 == 0b100:
            return a ^ b
        if funct3 == 0b101:
            return (to_signed(a) >> shamt) & MASK32 if funct7_bit5 else a >> shamt
        if funct3 == 0b110:
            return a | b
        return a & b

    @staticmethod
    def _branch_taken(funct3: int, a: int, b: int) -> bool:
        if funct3 == 0b000:
            return a == b
        if funct3 == 0b001:
            return a != b
        if funct3 == 0b100:
            return to_signed(a) < to_signed(b)
        if funct3 == 0b101:
            return to_signed(a) >= to_signed(b)
        if funct3 == 0b110:
            return a < b
        return a >= b

    def step(self) -> Commit | None:
        """Execute one instruction. Returns None (and sets halt_cause) on a trap."""
        if self.halted:
            return None

        pc = self.pc
        inst = self.mem[self._index(pc)]
        opcode = bits(inst, 6, 0)
        rd, rs1, rs2 = bits(inst, 11, 7), bits(inst, 19, 15), bits(inst, 24, 20)
        funct3, funct7 = bits(inst, 14, 12), bits(inst, 31, 25)
        a, b = self.regs[rs1], self.regs[rs2]

        imm_i = sign_extend(bits(inst, 31, 20), 12)
        imm_s = sign_extend(bits(inst, 31, 25) << 5 | bits(inst, 11, 7), 12)
        imm_b = sign_extend(bits(inst, 31, 31) << 12 | bits(inst, 7, 7) << 11
                            | bits(inst, 30, 25) << 5 | bits(inst, 11, 8) << 1, 13)
        imm_u = bits(inst, 31, 12) << 12
        imm_j = sign_extend(bits(inst, 31, 31) << 20 | bits(inst, 19, 12) << 12
                            | bits(inst, 20, 20) << 11 | bits(inst, 30, 21) << 1, 21)

        next_pc = (pc + 4) & MASK32
        rd_value = None
        mem_write = 0
        mem_addr = 0
        mem_wdata = 0

        try:
            if opcode == OP_LUI:
                rd_value = imm_u
            elif opcode == OP_AUIPC:
                rd_value = (pc + imm_u) & MASK32
            elif opcode == OP_JAL:
                rd_value = next_pc
                next_pc = (pc + imm_j) & MASK32
            elif opcode == OP_JALR:
                if funct3 != 0:
                    raise Trap(HALT_ILLEGAL)
                rd_value = next_pc
                next_pc = (a + imm_i) & ~1 & MASK32
            elif opcode == OP_BRANCH:
                if funct3 in (0b010, 0b011):
                    raise Trap(HALT_ILLEGAL)
                if self._branch_taken(funct3, a, b):
                    next_pc = (pc + imm_b) & MASK32
            elif opcode == OP_LOAD:
                if funct3 in (0b011, 0b110, 0b111):
                    raise Trap(HALT_ILLEGAL)
                mem_addr = (a + imm_i) & MASK32
                if self._misaligned(funct3, mem_addr):
                    raise Trap(HALT_MEM_MISALIGN)
                rd_value = self._load(funct3, mem_addr)
            elif opcode == OP_STORE:
                if funct3 > 0b010:
                    raise Trap(HALT_ILLEGAL)
                mem_addr = (a + imm_s) & MASK32
                if self._misaligned(funct3, mem_addr):
                    raise Trap(HALT_MEM_MISALIGN)
                mem_write, mem_wdata = 1, b
            elif opcode == OP_IMM:
                if funct3 == 0b001 and funct7 != 0x00:
                    raise Trap(HALT_ILLEGAL)
                if funct3 == 0b101 and funct7 not in (0x00, 0x20):
                    raise Trap(HALT_ILLEGAL)
                shift_op = funct3 in (0b001, 0b101)
                rd_value = self._alu(funct3, (funct7 >> 5) & 1 if funct3 == 0b101 else 0,
                                     a, bits(inst, 24, 20) if shift_op else imm_i)
            elif opcode == OP_REG:
                if funct7 != 0x00 and not (funct7 == 0x20 and funct3 in (0b000, 0b101)):
                    raise Trap(HALT_ILLEGAL)
                rd_value = self._alu(funct3, (funct7 >> 5) & 1, a, b)
            elif opcode == OP_MISC_MEM:
                if funct3 != 0:
                    raise Trap(HALT_ILLEGAL)  # FENCE retires as a NOP
            elif opcode == OP_SYSTEM:
                if bits(inst, 31, 7) == 0:
                    raise Trap(HALT_ECALL)
                if bits(inst, 31, 20) == 0x001 and bits(inst, 19, 7) == 0:
                    raise Trap(HALT_EBREAK)
                raise Trap(HALT_ILLEGAL)
            else:
                raise Trap(HALT_ILLEGAL)

            if next_pc & 3:
                raise Trap(HALT_FETCH_MISALIGN)
        except Trap as trap:
            self.halted = True
            self.halt_cause = trap.cause
            return None

        # Commit.
        if mem_write:
            self._store(funct3, mem_addr, mem_wdata)
        if rd_value is not None and rd != 0:
            self.regs[rd] = rd_value & MASK32
        self.pc = next_pc

        return Commit(
            pc=pc,
            inst=inst,
            next_pc=next_pc,
            rd=rd if rd_value is not None else 0,
            rd_wdata=(rd_value & MASK32) if (rd_value is not None and rd != 0) else 0,
            mem_write=mem_write,
            mem_addr=mem_addr,
            mem_wdata=mem_wdata,
        )

    def run(self, max_steps: int = 10000) -> list[Commit]:
        trace = []
        for _ in range(max_steps):
            commit = self.step()
            if commit is None:
                break
            trace.append(commit)
        return trace


def demo() -> None:
    """Self-check: run a small program and verify the architectural result."""
    from verif.asm import assemble

    # Sum 1..10, then halt. Result in a0 should be 55.
    program = assemble("""
        li   a0, 0
        li   t0, 1
    loop:
        add  a0, a0, t0
        addi t0, t0, 1
        li   t1, 11
        blt  t0, t1, loop
        ecall
    """)
    iss = Iss(program, words=256)
    trace = iss.run()
    assert iss.halt_cause == HALT_ECALL, iss.halt_cause
    assert iss.regs[10] == 55, iss.regs[10]
    assert trace[0].pc == 0 and trace[0].rd == 10

    # Loads and stores round-trip, including sign extension.
    program = assemble("""
        li   t0, 0x40
        li   t1, -2
        sw   t1, 0(t0)
        lb   a0, 0(t0)
        lhu  a1, 0(t0)
        lw   a2, 0(t0)
        ebreak
    """)
    iss = Iss(program, words=256)
    iss.run()
    assert iss.halt_cause == HALT_EBREAK
    assert iss.regs[10] == 0xFFFF_FFFE, hex(iss.regs[10])
    assert iss.regs[11] == 0x0000_FFFE, hex(iss.regs[11])
    assert iss.regs[12] == 0xFFFF_FFFE, hex(iss.regs[12])

    # An illegal word halts with the right cause and retires nothing.
    iss = Iss([0xFFFF_FFFF], words=256)
    assert iss.run() == []
    assert iss.halt_cause == HALT_ILLEGAL

    # x0 stays zero no matter what is written to it.
    iss = Iss(assemble("li x0, 5\necall"), words=256)
    iss.run()
    assert iss.regs[0] == 0
    print("iss demo OK")


if __name__ == "__main__":
    demo()
