"""cocotb testbench for rtl/regfile.sv.

Drives random reads and writes against a 32-entry Python list. Inputs change on
the falling edge; the combinational read ports are checked just before the
rising edge, which also proves a write isn't visible until the clock edge.
"""

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer


async def reset(dut) -> None:
    dut.rst.value = 1
    dut.we.value = 0
    dut.rd_addr.value = 0
    dut.rd_data.value = 0
    dut.rs1_addr.value = 0
    dut.rs2_addr.value = 0
    for _ in range(2):
        await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.rst.value = 0


async def read(dut, rs1: int, rs2: int) -> tuple[int, int]:
    dut.rs1_addr.value = rs1
    dut.rs2_addr.value = rs2
    await Timer(1, unit="ns")
    return dut.rs1_data.value.to_unsigned(), dut.rs2_data.value.to_unsigned()


@cocotb.test()
async def regfile_reset_clears_all(dut):
    Clock(dut.clk, 10, unit="ns").start()
    await reset(dut)
    for r in range(32):
        v1, v2 = await read(dut, r, r)
        assert v1 == 0 and v2 == 0, f"x{r} not zero after reset: rs1={v1:#x} rs2={v2:#x}"


@cocotb.test()
async def regfile_x0_hardwired(dut):
    Clock(dut.clk, 10, unit="ns").start()
    await reset(dut)
    dut.we.value = 1
    dut.rd_addr.value = 0
    dut.rd_data.value = 0xFFFF_FFFF
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.we.value = 0
    v1, v2 = await read(dut, 0, 0)
    assert v1 == 0 and v2 == 0, "write to x0 was not ignored"


@cocotb.test()
async def regfile_random_rw(dut):
    Clock(dut.clk, 10, unit="ns").start()
    await reset(dut)
    model = [0] * 32

    for cycle in range(3000):
        rs1, rs2 = random.randrange(32), random.randrange(32)
        we = random.random() < 0.7
        rd, data = random.randrange(32), random.getrandbits(32)

        dut.we.value = int(we)
        dut.rd_addr.value = rd
        dut.rd_data.value = data
        v1, v2 = await read(dut, rs1, rs2)
        assert v1 == model[rs1], f"cycle {cycle}: x{rs1} read 0x{v1:08x}, expected 0x{model[rs1]:08x}"
        assert v2 == model[rs2], f"cycle {cycle}: x{rs2} read 0x{v2:08x}, expected 0x{model[rs2]:08x}"

        await RisingEdge(dut.clk)
        if we and rd != 0:
            model[rd] = data
        await FallingEdge(dut.clk)
