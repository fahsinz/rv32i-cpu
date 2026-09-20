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
  decoder.sv         instruction -> datapath control signals
  branch_cmp.sv      branch condition evaluation (signed and unsigned)
  memory.sv          unified byte-addressed memory, sub-word loads and stores
  pc_unit.sv         program counter register and next-PC selection
verif/
  sim.py             cocotb runner wrapper (build + run + result check)
  test_unit.py       pytest entry for block-level tests
  unit/tb_*.py       cocotb testbenches, one per block
  isa.py             opcode/control encodings + instruction builders
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

**Decoder.** Control signals default to "do nothing", and each opcode only turns
on what it needs. Any encoding that is not RV32I (a bad funct3 on a branch, an
RV64 load width, a wrong funct7 on an R-type op) raises `illegal`, which then
forces every side-effect signal low, so a malformed instruction can never write
a register or memory. The testbench compares all 15 control outputs against a
Python reference over directed encodings, randomly built legal instructions, and
5,000 random words.

**Branch comparator.** Kept out of the ALU so the ALU stays free to compute the
branch target, and so the signed/unsigned distinction lives in one small block.
Its test pairs values that compare one way signed and the other way unsigned.

**Memory.** One array serves both an instruction read port and a data port, so
programs and data share an address space. Storage is word-wide: narrow accesses
select a lane from the addressed word and merge under byte enables, the way an
SRAM with byte enables behaves. Halfword and word accesses that are not aligned
raise `d_misaligned`, and a misaligned store is suppressed rather than writing
the wrong lane. Addresses wrap inside the array, so a runaway program cannot
index past the end of the model.

**PC unit.** Holds the PC and picks the next one: JALR takes the ALU result with
bit 0 cleared (required by the spec), branches and JAL add the immediate to the
current PC, everything else is PC+4. `misaligned_target` reports a next PC that
is not 4-byte aligned so the core can trap instead of fetching it.

## Verification approach

Each block is checked against an independent Python reference over directed
corner cases and randomized stimulus. Passing tests alone prove little, so every
block is also validated by **bug injection**: known bugs are planted in scratch
copies of the RTL and the suite must fail on each one. All 32 bugs planted so far
(SRAI decoded as SRLI, JALR skipping the link address, LB not sign-extending,
misaligned stores not blocked, and others) were caught.

Random tests print their seed; re-run a specific one with
`$env:COCOTB_RANDOM_SEED="1234"`.
