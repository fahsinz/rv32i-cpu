// pc_unit.sv
// Program counter register and next-PC selection.
//
// JALR clears bit 0 of its computed target, as the spec requires; the target
// itself arrives from the ALU as rs1 + imm. Branches and JAL add the immediate
// to the current PC. `misaligned_target` reports a next PC that is not 4-byte
// aligned, which the core turns into a trap rather than fetching it.

module pc_unit #(
  parameter logic [31:0] RESET_PC = 32'h0000_0000
) (
  input  logic        clk,
  input  logic        rst,
  input  logic        stall,        // hold the PC (used when the core halts)

  input  logic        branch,       // decoder says this is a branch
  input  logic        taken,        // branch comparator result
  input  logic        jump,         // JAL
  input  logic        jalr,         // JALR

  input  logic [31:0] imm,
  input  logic [31:0] alu_result,   // rs1 + imm, for JALR

  output logic [31:0] pc,
  output logic [31:0] pc_plus4,
  output logic [31:0] pc_next,
  output logic        misaligned_target
);

  assign pc_plus4 = pc + 32'd4;

  always_comb begin
    if (jalr)                        pc_next = {alu_result[31:1], 1'b0};
    else if (jump || (branch && taken)) pc_next = pc + imm;
    else                             pc_next = pc_plus4;
  end

  assign misaligned_target = |pc_next[1:0];

  always_ff @(posedge clk) begin
    if (rst)         pc <= RESET_PC;
    else if (!stall) pc <= pc_next;
  end

endmodule
