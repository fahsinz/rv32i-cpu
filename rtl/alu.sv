// alu.sv
// Arithmetic/logic unit covering every RV32I integer operation.
// Shifts use only b[4:0], matching the spec for both SLL/SRL/SRA and the
// shamt field of SLLI/SRLI/SRAI.

module alu
  import rv32i_pkg::*;
(
  input  logic [31:0] a,
  input  logic [31:0] b,
  input  logic [3:0]  op,
  output logic [31:0] y
);

  logic [4:0] shamt;
  assign shamt = b[4:0];

  always_comb begin
    case (op)
      ALU_ADD:  y = a + b;
      ALU_SUB:  y = a - b;
      ALU_SLL:  y = a << shamt;
      ALU_SLT:  y = {31'b0, $signed(a) < $signed(b)};
      ALU_SLTU: y = {31'b0, a < b};
      ALU_XOR:  y = a ^ b;
      ALU_SRL:  y = a >> shamt;
      ALU_SRA:  y = $signed(a) >>> shamt;
      ALU_OR:   y = a | b;
      ALU_AND:  y = a & b;
      default:  y = 32'b0;
    endcase
  end

endmodule
