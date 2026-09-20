// decoder.sv
// Main instruction decoder: turns a 32-bit instruction into datapath control.
// Anything that is not a defined RV32I encoding raises `illegal`, which also
// suppresses every architectural side effect (register and memory writes), so
// a bad instruction can never corrupt state.

module decoder
  import rv32i_pkg::*;
(
  input  logic [31:0] inst,

  output logic [3:0]  alu_op,
  output logic [1:0]  alu_a_sel,
  output logic        alu_b_sel,
  output logic [2:0]  imm_sel,

  output logic        reg_write,
  output logic [1:0]  wb_sel,

  output logic        mem_read,
  output logic        mem_write,
  output logic [2:0]  mem_op,     // funct3: access width and signedness

  output logic        branch,
  output logic        jump,       // JAL
  output logic        jalr,
  output logic        ecall,
  output logic        ebreak,
  output logic        illegal
);

  logic [6:0] opcode, funct7;
  logic [2:0] funct3;

  assign opcode = inst[6:0];
  assign funct3 = inst[14:12];
  assign funct7 = inst[31:25];

  always_comb begin
    // Defaults: do nothing observable.
    alu_op    = ALU_ADD;
    alu_a_sel = ALU_A_RS1;
    alu_b_sel = ALU_B_IMM;
    imm_sel   = IMM_I;
    reg_write = 1'b0;
    wb_sel    = WB_ALU;
    mem_read  = 1'b0;
    mem_write = 1'b0;
    mem_op    = funct3;
    branch    = 1'b0;
    jump      = 1'b0;
    jalr      = 1'b0;
    ecall     = 1'b0;
    ebreak    = 1'b0;
    illegal   = 1'b0;

    case (opcode)
      OP_LUI: begin
        alu_a_sel = ALU_A_ZERO;
        imm_sel   = IMM_U;
        reg_write = 1'b1;
      end

      OP_AUIPC: begin
        alu_a_sel = ALU_A_PC;
        imm_sel   = IMM_U;
        reg_write = 1'b1;
      end

      OP_JAL: begin
        imm_sel   = IMM_J;
        reg_write = 1'b1;
        wb_sel    = WB_PC4;
        jump      = 1'b1;
      end

      OP_JALR: begin
        if (funct3 != 3'b000) begin
          illegal = 1'b1;
        end else begin
          reg_write = 1'b1;
          wb_sel    = WB_PC4;
          jalr      = 1'b1;  // ALU makes rs1+imm; the PC logic clears bit 0
        end
      end

      OP_BRANCH: begin
        imm_sel = IMM_B;
        if (funct3 == 3'b010 || funct3 == 3'b011) illegal = 1'b1;
        else                                      branch  = 1'b1;
      end

      OP_LOAD: begin
        if (funct3 == 3'b011 || funct3 == 3'b110 || funct3 == 3'b111) begin
          illegal = 1'b1;  // LD / LWU are RV64 only
        end else begin
          reg_write = 1'b1;
          wb_sel    = WB_MEM;
          mem_read  = 1'b1;
        end
      end

      OP_STORE: begin
        imm_sel = IMM_S;
        if (funct3[2] || funct3[1:0] == 2'b11) illegal   = 1'b1;
        else                                   mem_write = 1'b1;
      end

      OP_IMM: begin
        reg_write = 1'b1;
        // SRAI is the only I-type op that reads funct7[5]; for the others those
        // bits are part of the immediate.
        alu_op = (funct3 == 3'b101) ? {funct7[5], funct3} : {1'b0, funct3};
        if (funct3 == 3'b001 && funct7 != 7'b0000000) illegal = 1'b1;
        if (funct3 == 3'b101 && funct7 != 7'b0000000 && funct7 != 7'b0100000) illegal = 1'b1;
      end

      OP_REG: begin
        alu_b_sel = ALU_B_RS2;
        reg_write = 1'b1;
        alu_op    = {funct7[5], funct3};
        // funct7 = 0x20 is legal only for SUB and SRA.
        if (funct7 != 7'b0000000 &&
            !(funct7 == 7'b0100000 && (funct3 == 3'b000 || funct3 == 3'b101))) illegal = 1'b1;
      end

      OP_MISC_MEM: begin
        if (funct3 != 3'b000) illegal = 1'b1;  // FENCE retires as a NOP
      end

      OP_SYSTEM: begin
        if (inst[31:7] == 25'b0)                                ecall   = 1'b1;
        else if (inst[31:20] == 12'h001 && inst[19:7] == 13'b0) ebreak  = 1'b1;
        else                                                    illegal = 1'b1;
      end

      default: illegal = 1'b1;
    endcase

    if (illegal) begin
      reg_write = 1'b0;
      mem_read  = 1'b0;
      mem_write = 1'b0;
      branch    = 1'b0;
      jump      = 1'b0;
      jalr      = 1'b0;
      ecall     = 1'b0;
      ebreak    = 1'b0;
    end
  end

endmodule
