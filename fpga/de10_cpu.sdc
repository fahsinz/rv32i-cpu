# Timing constraints for the CPU build.
#
# One real clock: the 50 MHz oscillator. Everything else on the board is a
# switch, a button or an LED, which have no timing relationship to it, so those
# paths are cut. What remains for the Timing Analyzer to judge is the CPU logic
# itself, which is what the Fmax number should be about.

create_clock -name clk_50 -period 20.000 [get_ports {MAX10_CLK1_50}]

derive_clock_uncertainty

# Human-speed inputs and outputs.
set_false_path -from [get_ports {SW[*]}] -to [all_registers]
set_false_path -from [get_ports {KEY[*]}] -to [all_registers]
set_false_path -from * -to [get_ports {LEDR[*]}]
set_false_path -from * -to [get_ports {HEX0[*]}]
set_false_path -from * -to [get_ports {HEX1[*]}]
set_false_path -from * -to [get_ports {HEX2[*]}]
set_false_path -from * -to [get_ports {HEX3[*]}]
set_false_path -from * -to [get_ports {HEX4[*]}]
set_false_path -from * -to [get_ports {HEX5[*]}]

# The CPU advances only when step_en is high, and step_en is never high on two
# consecutive clocks (see soc_top.sv), so logic inside the processor has two
# clock periods to settle rather than one. Without this the analyzer judges the
# single-cycle datapath against a 20 ns budget it was never asked to meet.
# No -to restriction on purpose: the register watch in soc_top (watch_value)
# only loads when commit_valid is high, and commit_valid already includes
# step_en, so paths out of the CPU advance at most every other clock too.
# Restricting this to CPU-internal paths left those debug paths failing at
# -3.7 ns, from the memory address register to watch_value[*].
set_multicycle_path -setup 2 -from [get_registers {*u_soc|*}]
set_multicycle_path -hold  1 -from [get_registers {*u_soc|*}]
