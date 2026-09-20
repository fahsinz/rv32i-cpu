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
  //0x00 = 0000000
  //0x20 = 0010000 = 010000
  //[func7[5],funct3] since for func7 the only bit that changes is bit 5
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

  // ---------------------------------------------------------------------------
  // Datapath mux selects (driven by the decoder)
  // ---------------------------------------------------------------------------
  localparam logic [1:0] ALU_A_RS1  = 2'd0;
  localparam logic [1:0] ALU_A_PC   = 2'd1;  // AUIPC
  localparam logic [1:0] ALU_A_ZERO = 2'd2;  // LUI is just 0 + imm
  localparam logic       ALU_B_RS2  = 1'b0;
  localparam logic       ALU_B_IMM  = 1'b1;

  // Write-back source
  localparam logic [1:0] WB_ALU = 2'd0;
  localparam logic [1:0] WB_MEM = 2'd1;
  localparam logic [1:0] WB_PC4 = 2'd2;  // JAL / JALR link address

endpackage
