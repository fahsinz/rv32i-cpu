// soc_top.sv -- the RV32I core running on a DE10-Lite.
//
// Controls
//   KEY[0]            reset (hold, release to restart the program)
//   KEY[1]            single-step one instruction (slow mode only)
//   SW[9]             0 = slow/stepped, 1 = full speed (50 MHz)
//   SW[8]             0 = show PC, 1 = show the watched register
//   SW[4:0]           which register to watch
//
// Display
//   HEX5..HEX0        24-bit value selected by SW[8]
//   LEDR[0]           halted
//   LEDR[3:1]         halt cause (1 ECALL, 2 EBREAK, 3 illegal, 4/5 misaligned)
//   LEDR[9]           heartbeat, so you can see the board is alive
//
// The core is never clocked from a gate or a button: everything runs on the
// 50 MHz clock and advances only when step_en is high.

module soc_top (
  input  logic       MAX10_CLK1_50,
  input  logic [1:0] KEY,              // active low
  input  logic [9:0] SW,
  output logic [9:0] LEDR,
  output logic [7:0] HEX0,
  output logic [7:0] HEX1,
  output logic [7:0] HEX2,
  output logic [7:0] HEX3,
  output logic [7:0] HEX4,
  output logic [7:0] HEX5
);

  logic clk, rst;
  assign clk = MAX10_CLK1_50;
  assign rst = ~KEY[0];

  // ---------------------------------------------------------------------------
  // Slow tick: 50 MHz / 2^23, about 6 instructions per second, slow enough to
  // read the PC off the display.
  // ---------------------------------------------------------------------------
  logic [22:0] divider;
  logic        tick;

  always_ff @(posedge clk) divider <= divider + 1'b1;
  assign tick = (divider == '0);

  // ---------------------------------------------------------------------------
  // KEY[1] into a single clean pulse. A tactile switch bounces for a few
  // milliseconds, and without this one press would step many instructions.
  // ponytail: fixed ~1.3 ms counter debounce; make it a parameter only if a
  // different switch needs a different window.
  // ---------------------------------------------------------------------------
  logic        key_raw, key_sync, key_stable, key_prev, key_pulse;
  logic [15:0] debounce;

  always_ff @(posedge clk) begin
    key_raw  <= ~KEY[1];      // 1 while pressed
    key_sync <= key_raw;      // two stages, because the button is asynchronous

    if (key_sync != key_stable) begin
      debounce <= debounce + 1'b1;
      if (debounce == 16'hFFFF) begin
        key_stable <= key_sync;
        debounce   <= '0;
      end
    end else begin
      debounce <= '0;
    end

    key_prev  <= key_stable;
    key_pulse <= key_stable & ~key_prev;   // one cycle on the press edge
  end

  // ---------------------------------------------------------------------------
  // The CPU
  // ---------------------------------------------------------------------------
  logic        step_en;
  logic        halted;
  logic [2:0]  halt_cause;
  logic        commit_valid;
  logic [31:0] commit_pc, commit_inst, commit_next_pc, commit_rd_wdata;
  logic [4:0]  commit_rd;
  logic        commit_mem_write;
  logic [31:0] commit_mem_addr, commit_mem_wdata;

  // "Full speed" is every other cycle, not every cycle. The single-cycle
  // datapath closes timing at ~35 MHz on this device, not 50 MHz, so the CPU
  // advances on alternate clocks: 25 MHz of instructions from a 50 MHz clock,
  // one clock domain, no gated or derived clock. de10_cpu.sdc tells the Timing
  // Analyzer about the 2-cycle budget. The enable is never high twice in a row,
  // which is what makes that constraint legitimate.
  assign step_en = SW[9] ? divider[0] : (tick | key_pulse);

  // 64 words (256 bytes). The memory has two asynchronous read ports, so every
  // extra word widens two 32-bit muxes: 256 words would not place in reasonable
  // time on this device, and the critical path runs straight through them.
  soc #(
    .WORDS     (64),
    .INIT_FILE ("program.hex")
  ) u_soc (
    .clk              (clk),
    .rst              (rst),
    .step_en          (step_en),
    .halted           (halted),
    .halt_cause       (halt_cause),
    .commit_valid     (commit_valid),
    .commit_pc        (commit_pc),
    .commit_inst      (commit_inst),
    .commit_next_pc   (commit_next_pc),
    .commit_rd        (commit_rd),
    .commit_rd_wdata  (commit_rd_wdata),
    .commit_mem_write (commit_mem_write),
    .commit_mem_addr  (commit_mem_addr),
    .commit_mem_wdata (commit_mem_wdata)
  );

  // ---------------------------------------------------------------------------
  // Register watch. The commit trace already reports every register write, so
  // watching one register costs a comparator and a latch, with no extra read
  // port cut into the verified register file.
  // ---------------------------------------------------------------------------
  logic [31:0] watch_value;

  always_ff @(posedge clk) begin
    if (rst) begin
      watch_value <= 32'b0;
    end else if (commit_valid && commit_rd != 5'd0 && commit_rd == SW[4:0]) begin
      watch_value <= commit_rd_wdata;
    end
  end

  // ---------------------------------------------------------------------------
  // Display
  // ---------------------------------------------------------------------------
  logic [23:0] shown;
  assign shown = SW[8] ? watch_value[23:0] : commit_pc[23:0];

  seg7 u_hex0 (.value(shown[3:0]),   .segments(HEX0));
  seg7 u_hex1 (.value(shown[7:4]),   .segments(HEX1));
  seg7 u_hex2 (.value(shown[11:8]),  .segments(HEX2));
  seg7 u_hex3 (.value(shown[15:12]), .segments(HEX3));
  seg7 u_hex4 (.value(shown[19:16]), .segments(HEX4));
  seg7 u_hex5 (.value(shown[23:20]), .segments(HEX5));

  assign LEDR[0]   = halted;
  assign LEDR[3:1] = halt_cause;
  assign LEDR[8:4] = commit_rd;
  assign LEDR[9]   = divider[22];

endmodule
