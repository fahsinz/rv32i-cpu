// soc.sv  --  the core wired to one memory. This is what the scoreboard
// simulates and what goes on the FPGA. Programs arrive either through
// INIT_FILE ($readmemh) or by a testbench writing into the memory array.

module soc #(
  parameter int unsigned WORDS     = 4096,
  parameter              INIT_FILE = ""
) (
  input  logic        clk,
  input  logic        rst,
  input  logic        step_en,

  output logic        halted,
  output logic [2:0]  halt_cause,

  // Retirement trace, passed straight out for the scoreboard
  output logic        commit_valid,
  output logic [31:0] commit_pc,
  output logic [31:0] commit_inst,
  output logic [31:0] commit_next_pc,
  output logic [4:0]  commit_rd,
  output logic [31:0] commit_rd_wdata,
  output logic        commit_mem_write,
  output logic [31:0] commit_mem_addr,
  output logic [31:0] commit_mem_wdata
);

  logic [31:0] i_addr, i_rdata;
  logic [31:0] d_addr, d_wdata, d_rdata;
  logic [2:0]  d_op;
  logic        d_read, d_write, d_misaligned;

  core u_core (
    .clk              (clk),
    .rst              (rst),
    .step_en          (step_en),
    .i_addr           (i_addr),
    .i_rdata          (i_rdata),
    .d_addr           (d_addr),
    .d_op             (d_op),
    .d_read           (d_read),
    .d_write          (d_write),
    .d_wdata          (d_wdata),
    .d_rdata          (d_rdata),
    .d_misaligned     (d_misaligned),
    .commit_valid     (commit_valid),
    .commit_pc        (commit_pc),
    .commit_inst      (commit_inst),
    .commit_next_pc   (commit_next_pc),
    .commit_rd        (commit_rd),
    .commit_rd_wdata  (commit_rd_wdata),
    .commit_mem_write (commit_mem_write),
    .commit_mem_addr  (commit_mem_addr),
    .commit_mem_wdata (commit_mem_wdata),
    .halted           (halted),
    .halt_cause       (halt_cause)
  );

  memory #(
    .WORDS     (WORDS),
    .INIT_FILE (INIT_FILE)
  ) u_memory (
    .clk          (clk),
    .i_addr       (i_addr),
    .i_rdata      (i_rdata),
    .d_addr       (d_addr),
    .d_op         (d_op),
    .d_read       (d_read),
    .d_write      (d_write),
    .d_wdata      (d_wdata),
    .d_rdata      (d_rdata),
    .d_misaligned (d_misaligned)
  );

endmodule
