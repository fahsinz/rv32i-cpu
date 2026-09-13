// imm_gen.sv
// Reassembles and sign-extends the immediate for each RV32I instruction format.
// The sign bit is always inst[31], which is what lets real hardware start
// sign-extending before decode has finished.

module imm_gen
  import rv32i_pkg::*;
(
  input  logic [31:0] inst,
  input  logic [2:0]  imm_sel,
  output logic [31:0] imm
);

  always_comb begin
    case (imm_sel)
      IMM_I:   imm = {{20{inst[31]}}, inst[31:20]};
      IMM_S:   imm = {{20{inst[31]}}, inst[31:25], inst[11:7]};
      IMM_B:   imm = {{19{inst[31]}}, inst[31], inst[7], inst[30:25], inst[11:8], 1'b0};
      IMM_U:   imm = {inst[31:12], 12'b0};
      IMM_J:   imm = {{11{inst[31]}}, inst[31], inst[19:12], inst[20], inst[30:21], 1'b0};
      default: imm = 32'b0;
    endcase
  end

endmodule
