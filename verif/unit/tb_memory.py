"""cocotb testbench for rtl/memory.sv.

Checks the lane selection and sign extension of sub-word loads, the byte
enables of sub-word stores, and that a misaligned access is both flagged and
prevented from writing. The DUT is built with WORDS=256, so random addresses
also exercise the wrap-around behaviour.
"""

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer

from verif.bits import MASK32, as_int, sign_extend

WORDS = 256
BYTES = WORDS * 4

LOADS = {"LB": 0b000, "LH": 0b001, "LW": 0b010, "LBU": 0b100, "LHU": 0b101}
STORES = {"SB": 0b000, "SH": 0b001, "SW": 0b010}


class MemModel:
    """Word-addressed reference model matching memory.sv, including wrap-around."""

    def __init__(self) -> None:
        self.words = [0] * WORDS

    def index(self, addr: int) -> int:
        return (addr >> 2) % WORDS

    def misaligned(self, op: int, addr: int) -> bool:
        if op in (0b001, 0b101):
            return bool(addr & 1)
        if op == 0b010:
            return bool(addr & 3)
        return False

    def load(self, op: int, addr: int) -> int:
        word = self.words[self.index(addr)]
        off = addr & 3
        lane_b = (word >> (8 * off)) & 0xFF
        lane_h = (word >> 16) & 0xFFFF if addr & 2 else word & 0xFFFF
        if op == 0b000:
            return sign_extend(lane_b, 8)
        if op == 0b001:
            return sign_extend(lane_h, 16)
        if op == 0b100:
            return lane_b
        if op == 0b101:
            return lane_h
        return word

    def store(self, op: int, addr: int, data: int) -> None:
        if self.misaligned(op, addr):
            return
        idx, off = self.index(addr), addr & 3
        word = self.words[idx]
        if op == 0b000:
            mask = 0xFF << (8 * off)
            word = (word & ~mask & MASK32) | ((data & 0xFF) << (8 * off))
        elif op == 0b001:
            shift = 16 if addr & 2 else 0
            mask = 0xFFFF << shift
            word = (word & ~mask & MASK32) | ((data & 0xFFFF) << shift)
        else:
            word = data & MASK32
        self.words[idx] = word


async def setup(dut) -> MemModel:
    """Start the clock and zero the array.

    Every cocotb test shares one simulation, so the DUT keeps whatever previous
    tests wrote. Clearing here keeps the DUT and the fresh model in step.
    """
    dut.clk.value = 0
    Clock(dut.clk, 10, unit="ns").start()
    dut.d_read.value = 0
    dut.d_write.value = 0
    dut.d_addr.value = 0
    dut.d_op.value = 0
    dut.d_wdata.value = 0
    dut.i_addr.value = 0
    await FallingEdge(dut.clk)

    dut.d_write.value = 1
    dut.d_op.value = STORES["SW"]
    dut.d_wdata.value = 0
    for addr in range(0, BYTES, 4):
        dut.d_addr.value = addr
        await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.d_write.value = 0
    return MemModel()


async def do_store(dut, model: MemModel, op: int, addr: int, data: int) -> None:
    dut.d_write.value = 1
    dut.d_read.value = 0
    dut.d_op.value = op
    dut.d_addr.value = addr
    dut.d_wdata.value = data
    await Timer(1, unit="ns")
    exp_mis = int(model.misaligned(op, addr))
    got_mis = as_int(dut.d_misaligned)
    assert got_mis == exp_mis, f"store addr=0x{addr:08x} op={op:03b}: misaligned {got_mis}, expected {exp_mis}"
    await RisingEdge(dut.clk)
    model.store(op, addr, data)
    await FallingEdge(dut.clk)
    dut.d_write.value = 0


async def check_load(dut, model: MemModel, op: int, addr: int, note: str = "") -> None:
    """Drive a load and check it. Entered and left on a falling edge.

    Staying anchored to the clock matters: if the testbench changed inputs at an
    arbitrary time it would eventually do so exactly on a rising edge and race
    the clocked write, which real clock-aligned logic never does.
    """
    dut.d_read.value = 1
    dut.d_write.value = 0
    dut.d_op.value = op
    dut.d_addr.value = addr
    await Timer(1, unit="ns")
    exp_mis = int(model.misaligned(op, addr))
    got_mis = as_int(dut.d_misaligned)
    assert got_mis == exp_mis, f"load addr=0x{addr:08x} op={op:03b}: misaligned {got_mis}, expected {exp_mis}"
    got, exp = as_int(dut.d_rdata), model.load(op, addr)
    assert got == exp, f"load {note} addr=0x{addr:08x} op={op:03b}: got 0x{got:08x}, expected 0x{exp:08x}"
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)


@cocotb.test()
async def mem_lane_selection(dut):
    """Every byte and halfword lane of a known word reads back correctly."""
    model = await setup(dut)
    await do_store(dut, model, STORES["SW"], 0x20, 0x11223344)
    for off, expect_b in ((0, 0x44), (1, 0x33), (2, 0x22), (3, 0x11)):
        await check_load(dut, model, LOADS["LBU"], 0x20 + off, f"byte lane {off}")
        assert as_int(dut.d_rdata) == expect_b, f"byte lane {off} wrong"
    await check_load(dut, model, LOADS["LHU"], 0x20, "low half")
    assert as_int(dut.d_rdata) == 0x3344
    await check_load(dut, model, LOADS["LHU"], 0x22, "high half")
    assert as_int(dut.d_rdata) == 0x1122
    await check_load(dut, model, LOADS["LW"], 0x20, "word")
    assert as_int(dut.d_rdata) == 0x11223344


@cocotb.test()
async def mem_sign_extension(dut):
    """LB/LH sign-extend; LBU/LHU zero-extend."""
    model = await setup(dut)
    await do_store(dut, model, STORES["SW"], 0x40, 0x80FF7F01)
    for op, addr, exp in (
        (LOADS["LB"], 0x40, 0x00000001),
        (LOADS["LB"], 0x41, 0x0000007F),
        (LOADS["LB"], 0x42, 0xFFFFFFFF),
        (LOADS["LB"], 0x43, 0xFFFFFF80),
        (LOADS["LBU"], 0x43, 0x00000080),
        (LOADS["LH"], 0x40, 0x00007F01),
        (LOADS["LH"], 0x42, 0xFFFF80FF),
        (LOADS["LHU"], 0x42, 0x000080FF),
    ):
        await check_load(dut, model, op, addr)
        got = as_int(dut.d_rdata)
        assert got == exp, f"op={op:03b} addr=0x{addr:02x}: got 0x{got:08x}, expected 0x{exp:08x}"


@cocotb.test()
async def mem_sub_word_stores(dut):
    """A byte or halfword store must leave the other lanes alone."""
    model = await setup(dut)
    await do_store(dut, model, STORES["SW"], 0x60, 0xAAAAAAAA)
    await do_store(dut, model, STORES["SB"], 0x61, 0x5A)
    await check_load(dut, model, LOADS["LW"], 0x60, "after SB")
    assert as_int(dut.d_rdata) == 0xAAAA5AAA, f"got 0x{as_int(dut.d_rdata):08x}"
    await do_store(dut, model, STORES["SH"], 0x62, 0x1234)
    await check_load(dut, model, LOADS["LW"], 0x60, "after SH")
    assert as_int(dut.d_rdata) == 0x1234_5AAA, f"got 0x{as_int(dut.d_rdata):08x}"


@cocotb.test()
async def mem_misaligned_flags_and_blocks_write(dut):
    model = await setup(dut)
    await do_store(dut, model, STORES["SW"], 0x80, 0xDEADBEEF)
    for op, addr in ((LOADS["LH"], 0x81), (LOADS["LHU"], 0x83), (LOADS["LW"], 0x81),
                     (LOADS["LW"], 0x82), (LOADS["LW"], 0x83)):
        await check_load(dut, model, op, addr, "misaligned")
    # Byte accesses are never misaligned.
    for addr in range(0x80, 0x84):
        await check_load(dut, model, LOADS["LB"], addr, "byte always aligned")
        assert as_int(dut.d_misaligned) == 0

    # A misaligned store must not change memory.
    await do_store(dut, model, STORES["SW"], 0x82, 0x11111111)
    await check_load(dut, model, LOADS["LW"], 0x80, "after blocked store")
    assert as_int(dut.d_rdata) == 0xDEADBEEF, "misaligned store corrupted memory"


@cocotb.test()
async def mem_instruction_port(dut):
    """The instruction port sees data written through the data port."""
    model = await setup(dut)
    for addr, data in ((0x00, 0x00100093), (0x04, 0x00200113), (0x3FC, 0xFE000EE3)):
        await do_store(dut, model, STORES["SW"], addr, data)
    for addr, data in ((0x00, 0x00100093), (0x04, 0x00200113), (0x3FC, 0xFE000EE3)):
        dut.i_addr.value = addr
        await Timer(1, unit="ns")
        got = as_int(dut.i_rdata)
        assert got == data, f"i_addr=0x{addr:03x}: got 0x{got:08x}, expected 0x{data:08x}"


@cocotb.test()
async def mem_random(dut):
    """Random stores and loads, including addresses past the end of the array."""
    model = await setup(dut)
    for _ in range(2000):
        addr = random.randrange(BYTES * 2)  # half the addresses wrap
        if random.random() < 0.5:
            op = random.choice(list(STORES.values()))
            await do_store(dut, model, op, addr, random.getrandbits(32))
        else:
            op = random.choice(list(LOADS.values()))
            await check_load(dut, model, op, addr, "random")
