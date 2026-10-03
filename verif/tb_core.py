"""cocotb testbench for the whole core (rtl/soc.sv).

Every retired instruction is compared against the Python ISS: PC, instruction
word, next PC, destination register and its value, and any memory write. When
the program stops, the halt cause, all 32 registers, and every memory word are
compared too.

The programs are assembled in-process by verif/asm.py, so a test reads as
assembly rather than hex.
"""

import random
from collections import Counter

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer

from verif import coverage, randgen
from verif.asm import assemble
from verif.bits import as_int
from verif.iss import (HALT_EBREAK, HALT_ECALL, HALT_FETCH_MISALIGN, HALT_ILLEGAL,
                       HALT_MEM_MISALIGN, HALT_NONE, Commit, Iss)

WORDS = 1024  # must match the WORDS parameter the runner passes to soc

# Coverage accumulates across every test in this simulation; the last test checks it.
COVERAGE = Counter()


# ---------------------------------------------------------------------------
# Driving
# ---------------------------------------------------------------------------
async def load_and_reset(dut, program: list[int]) -> None:
    """Put a program in memory and bring the core out of reset on a falling edge."""
    assert len(program) <= WORDS, f"program needs {len(program)} words, memory holds {WORDS}"
    dut.clk.value = 0
    dut.rst.value = 1
    dut.step_en.value = 1
    Clock(dut.clk, 10, unit="ns").start()
    await FallingEdge(dut.clk)

    for i in range(WORDS):
        dut.u_memory.mem[i].value = program[i] if i < len(program) else 0

    # Reset clears the PC, the halt latch and all registers.
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.rst.value = 0
    await Timer(1, unit="ns")


async def advance(dut) -> None:
    """Retire the instruction in this cycle and settle mid-cycle on the next one."""
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    await Timer(1, unit="ns")


def read_commit(dut) -> Commit:
    return Commit(
        pc=as_int(dut.commit_pc),
        inst=as_int(dut.commit_inst),
        next_pc=as_int(dut.commit_next_pc),
        rd=as_int(dut.commit_rd),
        rd_wdata=as_int(dut.commit_rd_wdata),
        mem_write=as_int(dut.commit_mem_write),
        mem_addr=as_int(dut.commit_mem_addr),
        mem_wdata=as_int(dut.commit_mem_wdata),
    )


# ---------------------------------------------------------------------------
# Comparing
# ---------------------------------------------------------------------------
def compare_commit(got: Commit, exp: Commit, index: int, name: str) -> None:
    fields = ["pc", "inst", "next_pc", "rd", "rd_wdata", "mem_write"]
    if exp.mem_write:
        fields += ["mem_addr", "mem_wdata"]
    bad = [f"{f}: core 0x{getattr(got, f):08x}, model 0x{getattr(exp, f):08x}"
           for f in fields if getattr(got, f) != getattr(exp, f)]
    assert not bad, (
        f"{name}: instruction {index} mismatch "
        f"(model pc=0x{exp.pc:08x} inst=0x{exp.inst:08x})\n  " + "\n  ".join(bad)
    )


def compare_state(dut, iss: Iss, name: str, retired: int) -> None:
    for r in range(32):
        got = as_int(dut.u_core.u_regfile.regs[r])
        assert got == iss.regs[r], (
            f"{name}: after {retired} instructions x{r} is 0x{got:08x}, model 0x{iss.regs[r]:08x}"
        )
    for i in range(WORDS):
        got = as_int(dut.u_memory.mem[i])
        assert got == iss.mem[i], (
            f"{name}: after {retired} instructions memory word {i} "
            f"(byte 0x{i * 4:04x}) is 0x{got:08x}, model 0x{iss.mem[i]:08x}"
        )


async def run_program(dut, program: list[int], name: str, max_steps: int = 2000,
                      expect_halt: int | None = None) -> None:
    """Run a program on the core and the model, comparing every retirement."""
    await load_and_reset(dut, program)

    iss = Iss(program, words=WORDS)
    expected = iss.run(max_steps)

    retired = 0
    budget = len(expected) * 4 + 200
    while retired < len(expected):
        budget -= 1
        assert budget > 0, f"{name}: core stopped retiring after {retired} instructions"
        assert not as_int(dut.halted), (
            f"{name}: core halted after {retired} instructions, model expected {len(expected)}"
        )
        if as_int(dut.commit_valid):
            compare_commit(read_commit(dut), expected[retired], retired, name)
            coverage.sample(COVERAGE, expected[retired].inst, expected[retired])
            retired += 1
        await advance(dut)

    # The model stopped. If it trapped, give the core one more clock to latch it;
    # a trapping instruction changes no architectural state.
    if iss.halted:
        await advance(dut)
        assert as_int(dut.halted), f"{name}: model halted (cause {iss.halt_cause}), core did not"
        got_cause = as_int(dut.halt_cause)
        assert got_cause == iss.halt_cause, (
            f"{name}: halt cause {got_cause}, model {iss.halt_cause}"
        )
        # A halted core must sit on the faulting instruction so it can be
        # inspected, on the board as much as in simulation.
        frozen = as_int(dut.commit_pc)
        assert frozen == iss.pc, (
            f"{name}: halted at pc 0x{frozen:08x}, model faulted at 0x{iss.pc:08x}"
        )
        for _ in range(3):
            await advance(dut)
            assert as_int(dut.commit_pc) == frozen, f"{name}: PC moved while halted"
        COVERAGE[f"halt:{iss.halt_cause}"] += 1
    else:
        assert not as_int(dut.halted), f"{name}: core halted but model ran to the step limit"

    compare_state(dut, iss, name, retired)
    cocotb.log.info("%s: %d instructions retired, halt cause %d", name, retired, iss.halt_cause)


# ---------------------------------------------------------------------------
# Directed programs
# ---------------------------------------------------------------------------
PROGRAMS: dict[str, tuple[str, int]] = {
    "arithmetic": ("""
        li   t0, 100
        li   t1, 37
        add  a0, t0, t1
        sub  a1, t0, t1
        and  a2, t0, t1
        or   a3, t0, t1
        xor  a4, t0, t1
        slt  a5, t1, t0
        sltu a6, t0, t1
        addi a7, t0, -200
        slti s2, a7, 0
        sltiu s3, a7, 0
        xori s4, t0, -1
        ori  s5, t0, 0x7F
        andi s6, t0, 0x0F
        ecall
    """, HALT_ECALL),

    "shifts": ("""
        li   t0, -8
        li   t1, 3
        sll  a0, t0, t1
        srl  a1, t0, t1
        sra  a2, t0, t1
        slli a3, t0, 0
        srli a4, t0, 31
        srai a5, t0, 31
        slli a6, t0, 31
        srai a7, t0, 1
        ecall
    """, HALT_ECALL),

    "branches": ("""
        li   t0, 5
        li   t1, -5
        li   s0, 0
        beq  t0, t0, b1
        addi s0, s0, 1          # skipped
    b1: bne  t0, t1, b2
        addi s0, s0, 2          # skipped
    b2: blt  t1, t0, b3
        addi s0, s0, 4          # skipped
    b3: bge  t0, t1, b4
        addi s0, s0, 8          # skipped
    b4: bltu t0, t1, b5         # unsigned: 5 < huge, taken
        addi s0, s0, 16         # skipped
    b5: bgeu t1, t0, b6
        addi s0, s0, 32         # skipped
    b6: beq  t0, t1, b7         # not taken
        addi s0, s0, 64
    b7: bne  t0, t0, b8         # not taken
        addi s0, s0, 128
    b8: blt  t0, t1, b9         # not taken
        addi s0, s0, 256
    b9: bge  t1, t0, b10        # not taken
        addi s0, s0, 512
    b10: bltu t1, t0, b11       # not taken
        addi s0, s0, 1024
    b11: bgeu t0, t1, b12       # not taken
        addi s0, s0, 2048
    b12: ecall
    """, HALT_ECALL),

    "memory": ("""
        li   s0, 0x200
        li   t0, -2
        sw   t0, 0(s0)
        lw   a0, 0(s0)
        lb   a1, 0(s0)
        lbu  a2, 0(s0)
        lh   a3, 0(s0)
        lhu  a4, 0(s0)
        lb   a5, 1(s0)           # byte lane 1
        lbu  a6, 3(s0)           # byte lane 3
        lhu  a7, 2(s0)           # high halfword
        li   t1, 0x7F
        sb   t1, 5(s0)           # byte lane 1 of the next word
        li   t2, 0x1234
        sh   t2, 10(s0)          # high halfword of a later word
        lw   s2, 4(s0)
        lw   s3, 8(s0)
        ecall
    """, HALT_ECALL),

    "jumps_and_upper": ("""
        lui   a0, 0x12345
        auipc a1, 0
        auipc a2, 1
        jal   ra, sub1
        li    s0, 1
        j     after
    sub1:
        li    s1, 2
        ret
    after:
        la_target: auipc t0, 0
        addi  t0, t0, 12
        jalr  ra, 0(t0)
        li    s2, 3
        li    s3, 4
        ecall
    """, HALT_ECALL),

    "x0_and_immediate_edges": ("""
        li   x0, 5               # must stay zero
        add  x0, x0, x0
        addi a0, x0, 2047        # largest positive I-immediate
        addi a1, x0, -2048       # most negative I-immediate
        lui  a2, 0xFFFFF
        lui  a3, 0
        addi a4, a2, -1
        add  a5, x0, x0          # result zero
        sub  a6, x0, a0          # result negative
        nop
        ecall
    """, HALT_ECALL),

    "fibonacci": ("""
        li   t0, 0
        li   t1, 1
        li   t2, 10
    loop:
        beqz t2, done
        add  t3, t0, t1
        mv   t0, t1
        mv   t1, t3
        addi t2, t2, -1
        j    loop
    done:
        li   t4, 0x300
        sw   t0, 0(t4)
        mv   a0, t0
        ecall
    """, HALT_ECALL),

    "bubble_sort": ("""
        li   s0, 0x200           # array base
        li   s1, 8               # n
        li   t0, 0
    fill:                        # a[i] = n - i, so the array starts reversed
        beq  t0, s1, outer
        slli t1, t0, 2
        add  t1, s0, t1
        sub  t2, s1, t0
        sw   t2, 0(t1)
        addi t0, t0, 1
        j    fill
    outer:
        li   t3, 0               # swapped flag
        li   t0, 0
    inner:
        addi t4, s1, -1
        beq  t0, t4, check
        slli t1, t0, 2
        add  t1, s0, t1
        lw   t5, 0(t1)
        lw   t6, 4(t1)
        bge  t6, t5, noswap
        sw   t6, 0(t1)
        sw   t5, 4(t1)
        li   t3, 1
    noswap:
        addi t0, t0, 1
        j    inner
    check:
        bnez t3, outer
        ecall
    """, HALT_ECALL),

    "trap_ebreak": ("""
        li   a0, 1
        ebreak
        li   a0, 2
    """, HALT_EBREAK),

    "trap_illegal": ("""
        li   a0, 1
        .word 0xFFFFFFFF
        li   a0, 2
    """, HALT_ILLEGAL),

    "trap_misaligned_load": ("""
        li   t0, 0x204
        li   t1, 0xDEADBEEF
        sw   t1, 0(t0)
        li   a0, 0x123           # a0 must survive the trap untouched
        addi t0, t0, 1           # 0x205: misaligned for a word access
        lw   a0, 0(t0)
        li   a0, 2
    """, HALT_MEM_MISALIGN),

    "trap_misaligned_store": ("""
        li   t0, 0x202
        li   t1, 7
        sw   t1, 0(t0)
    """, HALT_MEM_MISALIGN),

    "trap_misaligned_jump": ("""
        li   t0, 0x202
        jalr x0, 0(t0)
        li   a0, 2
    """, HALT_FETCH_MISALIGN),
}


@cocotb.test()
async def core_directed_programs(dut):
    for name, (source, expect_halt) in PROGRAMS.items():
        await run_program(dut, assemble(source), name, expect_halt=expect_halt)


@cocotb.test()
async def core_random_programs(dut):
    """Constrained-random programs, compared instruction by instruction."""
    for i in range(12):
        program = randgen.random_program(60)
        await run_program(dut, program, f"random[{i}]", max_steps=300)


@cocotb.test()
async def core_random_long(dut):
    """A few longer programs, to get deeper into loops."""
    for i in range(3):
        program = randgen.random_program(200)
        await run_program(dut, program, f"random_long[{i}]", max_steps=800)


@cocotb.test()
async def core_step_enable_freezes(dut):
    """With step_en low the core must not move; raising it resumes exactly where it was."""
    program = assemble("""
        li   t0, 1
        addi t0, t0, 1
        addi t0, t0, 1
        addi t0, t0, 1
        ecall
    """)
    await load_and_reset(dut, program)

    for _ in range(2):
        await advance(dut)

    pc_before = as_int(dut.commit_pc)
    reg_before = as_int(dut.u_core.u_regfile.regs[5])  # t0
    dut.step_en.value = 0
    await Timer(1, unit="ns")
    assert not as_int(dut.commit_valid), "commit_valid must be low while stepping is disabled"
    for _ in range(5):
        await advance(dut)
        assert as_int(dut.commit_pc) == pc_before, "PC moved while step_en was low"
        assert as_int(dut.u_core.u_regfile.regs[5]) == reg_before, "register changed while step_en was low"

    dut.step_en.value = 1
    await Timer(1, unit="ns")
    assert as_int(dut.commit_valid), "commit_valid must return when stepping is re-enabled"
    await advance(dut)
    assert as_int(dut.commit_pc) == pc_before + 4, "core did not resume where it left off"


@cocotb.test()
async def core_functional_coverage(dut):
    """Gate on coverage: every required bin must have been hit by the tests above."""
    cocotb.log.info("functional coverage:\n%s", coverage.report(COVERAGE))
    gaps = coverage.missing(COVERAGE)
    assert not gaps, f"coverage holes: {gaps}"
