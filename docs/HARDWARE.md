# From RTL to the DE10-Lite

Step-by-step: compile the CPU, produce block diagrams and schematics, run
timing analysis, program the board, and test the running processor by hand.

Everything below assumes Quartus Prime Lite at `C:\altera_lite\25.1std` and a
DE10-Lite (MAX 10, `10M50DAF484C7G`). Commands are PowerShell, run from the
repo root unless stated otherwise.

---

## 1. Build the program the CPU will run

The CPU boots straight into whatever is in memory, so build that first.

```bash
python tools/build_program.py --run
```

This assembles [fpga/program.s](../fpga/program.s) into `fpga/program.hex`
(which `$readmemh` loads at power-up) and then runs the same program on the
golden model, printing what each register should end up holding:

```
model: 35 instructions retired, halted on ECALL
  x10 a0  = 0x00000037  (55)
```

**Know the answer before you look at the board.** If the board shows something
else, the hardware is wrong — not your expectation.

To run a different program, edit `fpga/program.s` (or point the tool at another
file) and re-run it. Memory holds 64 words (256 bytes) in this build, so programs must fit in
that. The simulation build uses 1,024 words; it is the same RTL with a
different parameter.

---

## 2. Compile for the board

Two projects live in `fpga/`:

| Revision | Top level | What it is |
|---|---|---|
| `de10_lite` | `top.sv` | Combinational ALU demo on the switches (no clock) |
| `de10_cpu` | `soc_top.sv` | The full CPU with program memory, stepping, and displays |

Command line (repeatable, and what CI would use):

```bash
cd fpga; C:\altera_lite\25.1std\quartus\bin64\quartus_sh.exe --flow compile de10_cpu
```

Or in the GUI: **File → Open Project → `fpga/de10_cpu.qpf`**, then
**Processing → Start Compilation** (Ctrl+L).

The compile runs four stages, and it is worth knowing which is which, because
they fail for different reasons:

1. **Analysis & Synthesis** — turns SystemVerilog into generic gates. Failures here are language or naming errors.
2. **Fitter** — places and routes into real MAX 10 resources, honouring your pin assignments. Failures here mean "does not fit" or "illegal pin".
3. **Assembler** — writes the `.sof` bitstream.
4. **Timing Analyzer** — checks the design meets the clock constraint.

Resource usage lands in `fpga/output_files/de10_cpu.fit.summary`.

---

## 3. Block diagrams and schematics

Quartus will draw your design for you, at three different levels.

### 3a. RTL Viewer — the schematic of what you wrote

**Tools → Netlist Viewers → RTL Viewer** (after Analysis & Synthesis).

This is the one for a README or a report: it shows your modules as boxes with
named ports and the wires between them. Useful moves:

- The **Hierarchy** pane on the left navigates the design. Start at `soc_top`, then double-click `u_soc`, then `u_core` to see the datapath with the decoder, ALU, register file and PC unit wired together.
- Double-click any box to descend into it; the breadcrumb at the top walks back out.
- Right-click a net → **Highlight Net** to trace one signal through the drawing.
- To export: **File → Export…** with the viewer focused, and choose PNG or JPEG. For a crisp image, zoom to fit first (the export captures the current view).

Capture one image per level: `u_core` for the datapath, `u_decoder` for the
control logic, `u_alu` for a leaf block.

### 3b. Technology Map Viewer — the schematic of what you actually got

**Tools → Netlist Viewers → Technology Map Viewer (Post-Fitting)**.

The same design after the fitter, in terms of real LUTs and registers. Use it
when you want to show that `alu.sv` became a specific pile of 4-input LUTs, or
to see how the memory mux turned out. This is also where you discover that an
innocent line of RTL cost 500 LUTs.

### 3c. Chip Planner — the floorplan

**Tools → Chip Planner**. Shows where on the die your logic landed and how
congested the routing is. Mostly a picture for the README, but genuinely useful
when timing fails because two connected blocks are placed far apart.

### 3d. The architecture diagram you draw yourself

Tool-generated schematics are accurate but ugly, and nobody reads an auto-drawn
spaghetti diagram. For the README, draw the datapath deliberately — the one in
the [main README](../README.md) is a Mermaid diagram, which GitHub renders
directly and which you can edit as text. Keep the generated RTL Viewer image as
evidence, and the hand-drawn one as explanation.

---

## 4. Timing analysis

### Why there is an `.sdc`

The Timing Analyzer has no idea how fast you intend to run. [de10_cpu.sdc](../fpga/de10_cpu.sdc)
tells it two things: the 50 MHz oscillator is a clock with a 20 ns period, and
the switches, buttons and displays have no timing relationship to it, so paths
to and from them should not be analysed. Without the clock definition the
compiler barely optimizes and reports nothing useful — that is exactly the
`Synopsys Design Constraints File file not found` critical warning the ALU demo
project emits, since it has no registers to constrain.

### Running it

GUI: **Tools → Timing Analyzer**, then in the Tasks pane run **Report Fmax
Summary** and **Report Setup Summary**. Command line:

```bash
cd fpga; C:\altera_lite\25.1std\quartus\bin64\quartus_sta.exe de10_cpu -c de10_cpu
```

The full report is written to `fpga/output_files/de10_cpu.sta.rpt`.

### Reading the numbers

- **Fmax** — the highest frequency this clock could run at. Above 50 MHz means the design closes timing on this board.
- **Setup slack** — time to spare on the worst path. Positive is pass, negative is fail; `-1.2 ns` means the path needs 1.2 ns more than the clock allows.
- **Hold slack** — whether data arrives too *early*. Rarely a problem inside one clock domain.
- The **worst-case path** listing shows the exact chain of logic that limits you, cell by cell. That is the thing to fix, not the design in general.

In this CPU the critical path runs through the longest single-cycle chain:
PC → instruction memory read mux → decode → register file read → ALU → data
memory read mux → write-back. Everything a single-cycle machine does is on that
one path, which is the classic reason single-cycle designs clock slowly.

### What this design actually measured, and what was done about it

The first clean compile **failed timing**, and the numbers are worth keeping:

```
Fmax (slow 85C model)   35.16 MHz
clk_50 setup slack      -8.440 ns
Critical Warning (332148): Timing requirements not met
```

The core needs ~28 ns to get through that chain, and a 50 MHz clock offers 20.
No amount of fitter effort closes an 8 ns gap.

The fix in this repo: **the CPU advances every other clock.** `step_en` is a
clock enable that already existed for single-stepping, so full speed became
`divider[0]` instead of constant 1 — one instruction per two clocks, 25 MHz of
instructions from the 50 MHz oscillator, still a single clock domain with no
gated or derived clock. [de10_cpu.sdc](../fpga/de10_cpu.sdc) then tells the
analyzer that logic inside the CPU has two periods to settle:

```tcl
set_multicycle_path -setup 2 -from [get_registers {*u_soc|*}] -to [get_registers {*u_soc|*}]
set_multicycle_path -hold  1 -from [get_registers {*u_soc|*}] -to [get_registers {*u_soc|*}]
```

That constraint is only honest because the enable is never high on two
consecutive clocks. Writing a multicycle exception for a path that really does
run every cycle is how people ship chips that fail in the lab.

**It failed again at -3.748 ns**, and the fix came from asking which path:

```tcl
# fpga/worst_path.tcl -- run with: quartus_sta -t worst_path.tcl
project_open de10_cpu -revision de10_cpu
create_timing_netlist
read_sdc
update_timing_netlist
report_timing -setup -npaths 4 -detail summary -file worst_path.txt
project_close
```

```
; -3.748 ; soc:u_soc|memory:u_memory|...|ram_block1a0~portb_address_reg0 ; watch_value[23] ;
```

The remaining paths ran from inside the CPU to `watch_value` in `soc_top` � the
debug register watch, which is *outside* `u_soc` and so outside a constraint
written `-to [get_registers {*u_soc|*}]`. Dropping the `-to` restriction (the
watch only loads when `commit_valid` is high, which already includes `step_en`)
closed timing at **+5.205 ns**, total negative slack 0.000.

Two lessons worth more than the result: a constraint that covers most of the
design is not the same as one that covers the failing path, and `report_timing`
names the path so there is no need to guess.

### Other ways out, in order of effort

1. **Shrink memory.** The read mux over the memory array dominates, and not by a little: at `WORDS=256` the fitter ran over 15 minutes without placing, because two asynchronous read ports mean two 256:1 32-bit muxes. `WORDS=64` places in a couple of minutes. Quartus reports the array as "uninferred RAM logic ... due to asynchronous read logic", which is the warning to watch for.
2. **Slow the clock** with a PLL or a divider, instead of an enable. Equivalent in effect, but it adds a clock domain to constrain.
3. **Make memory synchronous** so each read gets its own cycle. This turns the single-cycle core into a multi-cycle one — a real design change, and the natural next project.
4. **Pipeline it.** The proper answer, and the reason real cores are pipelined.

---

## 5. Program the board

1. Connect the DE10-Lite by USB. The first time, Windows may need the **USB-Blaster** driver: Device Manager → the unknown device → Update driver → browse to `C:\altera_lite\25.1std\quartus\drivers\usb-blaster`.
2. Program it:

```bash
cd fpga; C:\altera_lite\25.1std\quartus\bin64\quartus_pgm.exe -m jtag -o "p;output_files/de10_cpu.sof"
```

Or GUI: **Tools → Programmer → Hardware Setup → USB-Blaster**, confirm the
`.sof` is listed with **Program/Configure** ticked, then **Start**.

`.sof` loads into RAM and is lost on power-off. To make it survive a power
cycle, convert to `.pof` (**File → Convert Programming Files**, output `.pof`
for the MAX 10 internal flash) and program that instead.

---

## 6. Testing the running CPU by hand

Controls built into [soc_top.sv](../fpga/soc_top.sv):

| Control | Effect |
|---|---|
| `KEY[0]` | Reset — hold and release to restart the program |
| `KEY[1]` | Single-step one instruction (slow mode only) |
| `SW[9]` | 0 = stepped/slow, 1 = full speed (one instruction every other 50 MHz clock = 25 MHz) |
| `SW[8]` | 0 = display the PC, 1 = display the watched register |
| `SW[4:0]` | Which register to watch (10 = `a0`) |
| `HEX5..HEX0` | The selected 24-bit value in hex |
| `LEDR[0]` | Halted |
| `LEDR[3:1]` | Halt cause: 1 ECALL, 2 EBREAK, 3 illegal, 4 misaligned data, 5 misaligned fetch |
| `LEDR[8:4]` | Destination register of the instruction currently retiring |
| `LEDR[9]` | Heartbeat — if this is not blinking, the clock or the bitstream is not running |

### Test 1 — does it compute?

Set `SW[9]=1` (full speed), `SW[8]=1` (watch register), `SW[4:0]=01010` (10 = `a0`).
Press and release `KEY[0]`.

Expect: `LEDR[0]` on, `LEDR[3:1]` = 001 (ECALL), display `000037` — that is 55,
the sum of 1..10, matching the model from step 1. The program finishes in under
a microsecond, so it looks instant.

### Test 2 — watch it execute

Set `SW[9]=0`, `SW[8]=0` (show PC). Reset.

Expect the display to walk `000000`, `000004`, `000008`, `00000C`, then bounce
between `00000C` and `000014` as the loop runs, and finally stop at `000020`
(the `ecall`) with `LEDR[0]` lit. Watching the PC jump backwards at the bottom
of a loop is the moment the thing stops being a simulation.

### Test 3 — single-step

With `SW[9]=0`, press `KEY[1]` repeatedly. Each press advances exactly one
instruction, because `step_en` is a clock enable with a debounced one-cycle
pulse (a verified behaviour: `core_step_enable_freezes` in the testbench).
Compare each PC against the listing from `build_program.py`.

### Test 4 — watch any register

Flip `SW[8]=1` and dial `SW[4:0]` to 5 (`t0`), 6 (`t1`) or 7 (`t2`). Against the
model output from step 1: `t0` = 11, `t1` = 11, `t2` = 0x80. The watch latch
updates whenever that register is written, so in slow mode you can see the
running total climb.

### Test 5 — make it fault on purpose

Prove the trap logic works on real hardware. Change the last line of
`fpga/program.s` to `ebreak`, then:

```bash
python tools/build_program.py --run; cd fpga; C:\altera_lite\25.1std\quartus\bin64\quartus_sh.exe --flow compile de10_cpu
```

Reset, and `LEDR[3:1]` should read 010 (EBREAK) instead of 001. Try
`.word 0xFFFFFFFF` for cause 3 (illegal), and `lw a0, 1(t2)` for cause 4
(misaligned load). The PC display freezes at the faulting instruction, which is
the behaviour the `frozen` check in the testbench enforces.

### When nothing works

In the order worth checking:

1. **`LEDR[9]` not blinking** — the bitstream is not running. Re-program, check the Programmer found a USB-Blaster, confirm the board is in RUN (not PROG) mode.
2. **Display dark or nonsense but heartbeat fine** — pin assignments. Cross-check the HEX locations in `de10_cpu.qsf` against the DE10-Lite User Manual; a wrong pin is the most common cause.
3. **Immediately halted with cause 3 (illegal)** — memory is empty, so the CPU executed zeros. `program.hex` was not loaded: confirm it sits in `fpga/` and that the compile log has no warning about `$readmemh` being ignored.
4. **Everything halted at PC 0** — reset is stuck. `KEY[0]` is active low; the design inverts it, so if reset looks permanently asserted check that pin.
5. **Works slow, misbehaves at full speed** — a timing failure. Go back to step 4 and read the Fmax number.

---

## 7. Signal Tap: an oscilloscope inside the chip

To see the commit trace on real hardware rather than in simulation:

1. **Tools → Signal Tap Logic Analyzer**.
2. Set the sample clock to `MAX10_CLK1_50` and depth to 1K.
3. Add nodes (**Edit → Add Nodes**, post-fit) for `commit_pc`, `commit_inst`, `commit_rd`, `commit_rd_wdata`, `halted`.
4. Trigger on `commit_valid` rising, or on `halted`.
5. Save as `de10_cpu.stp`, let Quartus add it to the project, recompile, program, then **Run Analysis**.

You get a waveform of your CPU actually retiring instructions on silicon — the
same signals the Python scoreboard checks in simulation. It costs a few hundred
LUTs and some M9K, which this design can spare.

---

## 8. Optional: gate-level simulation in Questa

The cocotb suite simulates RTL. To simulate the *synthesized* netlist (catching
anything synthesis changed), have Quartus write a gate-level netlist
(**Assignments → Settings → EDA Tool Settings → Simulation**, format Verilog,
"Generate netlist for functional simulation only") and simulate that with the
Questa FSE installed at `C:\altera_lite\25.1std\questa_fse`.

Worth doing once so you can say you did; the RTL scoreboard is where the real
coverage comes from.
