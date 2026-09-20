// branch_cmp.sv
// Branch condition evaluator. Kept separate from the ALU so the ALU stays free
// to compute the branch target, and so signed vs unsigned comparison lives in
// one small, exhaustively testable place.

module branch_cmp (
  input  logic [31:0] a,
  input  logic [31:0] b,
  input  logic [2:0]  funct3,
  output logic        taken
);

  always_comb begin
    case (funct3)
      3'b000:  taken = (a == b);                    // BEQ
      3'b001:  taken = (a != b);                    // BNE
      3'b100:  taken = ($signed(a) < $signed(b));   // BLT
      3'b101:  taken = ($signed(a) >= $signed(b));  // BGE
      3'b110:  taken = (a < b);                     // BLTU
      3'b111:  taken = (a >= b);                    // BGEU
      default: taken = 1'b0;                        // 010/011 are not RV32I
    endcase
  end

endmodule
