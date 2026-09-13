// rv32i_pkg.sv
// Shared encodings for the RV32I core: opcodes, ALU operations, immediate formats.

package rv32i_pkg;

  // ---------------------------------------------------------------------------
  // Base opcodes (inst[6:0])
  // ---------------------------------------------------------------------------
  localparam logic [6:0] OP_LUI      = 7'b0110111;
  localparam logic [6:0] OP_AUIPC    = 7'b0010111;
  localparam logic [6:0] OP_JAL      = 7'b1101111;
  localparam logic [6:0] OP_JALR     = 7'b1100111;
  localparam logic [6:0] OP_BRANCH   = 7'b1100011;
  localparam logic [6:0] OP_LOAD     = 7'b0000011;
  localparam logic [6:0] OP_STORE    = 7'b0100011;
  localparam logic [6:0] OP_IMM      = 7'b0010011;
  localparam logic [6:0] OP_REG      = 7'b0110011;
  localparam logic [6:0] OP_MISC_MEM = 7'b0001111;  // FENCE
  localparam logic [6:0] OP_SYSTEM   = 7'b1110011;  // ECALL / EBREAK

  // ---------------------------------------------------------------------------
  // ALU operations
  // Encoded as {funct7[5], funct3} so R-type instructions map straight onto the
  // ALU op with no translation table. I-type uses {1'b0, funct3}, except SRAI,
  // which carries funct7[5] in its immediate just like SRA.
  // ---------------------------------------------------------------------------
  localparam logic [3:0] ALU_ADD  = 4'b0_000;
  localparam logic [3:0] ALU_SLL  = 4'b0_001;
  localparam logic [3:0] ALU_SLT  = 4'b0_010;
  localparam logic [3:0] ALU_SLTU = 4'b0_011;
  localparam logic [3:0] ALU_XOR  = 4'b0_100;
  localparam logic [3:0] ALU_SRL  = 4'b0_101;
  localparam logic [3:0] ALU_OR   = 4'b0_110;
  localparam logic [3:0] ALU_AND  = 4'b0_111;
  localparam logic [3:0] ALU_SUB  = 4'b1_000;
  localparam logic [3:0] ALU_SRA  = 4'b1_101;

  // ---------------------------------------------------------------------------
  // Immediate formats (selects the bit-scramble in imm_gen)
  // ---------------------------------------------------------------------------
  localparam logic [2:0] IMM_I = 3'd0;
  localparam logic [2:0] IMM_S = 3'd1;
  localparam logic [2:0] IMM_B = 3'd2;
  localparam logic [2:0] IMM_U = 3'd3;
  localparam logic [2:0] IMM_J = 3'd4;

endpackage
