# rv32i-cpu

A single-cycle RISC-V **RV32I** core in SystemVerilog, verified with a Python
golden model, constrained-random tests, and a cocotb scoreboard.

> **Status:** Day 12 of 21 — CPU building blocks and their unit tests.
> See [docs/ROADMAP.md](docs/ROADMAP.md) for the full plan.

## Layout

```
rtl/                 synthesizable SystemVerilog
  rv32i_pkg.sv       opcodes, ALU op codes, immediate formats
  alu.sv             all RV32I integer operations
  regfile.sv         32 x 32-bit registers, x0 hardwired to zero
  imm_gen.sv         I/S/B/U/J immediate reassembly + sign extension
verif/
  sim.py             cocotb runner wrapper (build + run + result check)
  test_unit.py       pytest entry for block-level tests
  unit/tb_*.py       cocotb testbenches, one per block
  bits.py            bit helpers shared with the (upcoming) golden model
docs/ROADMAP.md
```

## Setup

Requires Python 3.10+ and [Icarus Verilog](https://steveicarus.github.io/iverilog/) 12+ on `PATH`.
Tested with Icarus Verilog 14.0, cocotb 2.1.0, and pytest 9.1 on Windows 11.

```bash
scoop install iverilog
```

```bash
python -m pip install -r requirements.txt
```

## Running tests

```bash
python -m pytest -v
```

Useful knobs (PowerShell syntax shown):

| Variable | Effect |
|----------|--------|
| `$env:WAVES="1"` | Dump waveforms to `sim_build/<block>/` (open with GTKWave) |
| `$env:COCOTB_RANDOM_SEED="1234"` | Replay a randomized run; every log prints the seed it used |
| `$env:SIM="verilator"` | Use a different cocotb-supported simulator |

Run one block: `python -m pytest -v -k alu`

## Design notes

**ALU op encoding.** ALU operations are encoded as `{funct7[5], funct3}`. R-type
instructions therefore feed their own bits straight into the ALU, and I-type
instructions use `{0, funct3}`. The one exception is SRAI, which carries the
`funct7[5]` bit in its immediate field.

**Register file.** It has two combinational read ports and one synchronous write
port. Writes to x0 are dropped at the write port, and reads of x0 are forced to
zero, so x0 reads as 0 whatever is stored. All registers reset to zero so the
RTL and the golden model start from identical architectural state.

**Immediate generator.** The sign bit is always `inst[31]` for every format. The
unit test sweeps a walking one across all 32 instruction bits for each format,
so a single miswired bit in the B- or J-type scramble fails the test.
