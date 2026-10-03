// core.sv  --  single-cycle RV32I core
//
// One instruction per clock: fetch, decode, read registers, compute, access
// data memory, write back, select the next PC. All in one cycle, so both memory
// reads are combinational.
//
// There is no trap handler. Anything that would raise an exception (illegal
// instruction, ECALL, EBREAK, a misaligned access or branch target) latches
// `halted` with a cause and freezes the machine, which is what a test needs.
//
// The commit_* port is a retirement trace in the spirit of RVFI: it reports
// what the instruction in this cycle did, so a scoreboard can compare the core
// against a golden model instruction by instruction without looking inside.

module core
  import rv32i_pkg::*;
(
  input  logic        clk,
  input  logic        rst,
  // Hold the core still without gating its clock: a clean clock enable, which
  // is what lets the FPGA build single-step the CPU from a push-button.
  input  logic        step_en,

  // Instruction fetch (combinational read)
  output logic [31:0] i_addr,
  input  logic [31:0] i_rdata,

  // Data memory
  output logic [31:0] d_addr,
  output logic [2:0]  d_op,
  output logic        d_read,
  output logic        d_write,
  output logic [31:0] d_wdata,
  input  logic [31:0] d_rdata,
  input  logic        d_misaligned,

  // Retirement trace
  output logic        commit_valid,
  output logic [31:0] commit_pc,
  output logic [31:0] commit_inst,
  output logic [31:0] commit_next_pc,
  output logic [4:0]  commit_rd,
  output logic [31:0] commit_rd_wdata,
  output logic        commit_mem_write,
  output logic [31:0] commit_mem_addr,
  output logic [31:0] commit_mem_wdata,

  output logic        halted,
  output logic [2:0]  halt_cause
);

  logic [31:0] inst;
  logic [31:0] pc, pc_plus4, pc_next;
  logic [31:0] imm, rs1_data, rs2_data, alu_a, alu_b, alu_y, wb_data;

  logic [3:0]  alu_op;
  logic [1:0]  alu_a_sel, wb_sel;
  logic        alu_b_sel;
  logic [2:0]  imm_sel, mem_op;
  logic        reg_write, mem_read, mem_write;
  logic        branch, jump, jalr, ecall, ebreak, illegal;
  logic        taken, misaligned_target;
  logic        trap;
  logic [2:0]  trap_cause;

  assign i_addr = pc;
  assign inst   = i_rdata;

  // ---------------------------------------------------------------------------
  // Decode
  // ---------------------------------------------------------------------------
  decoder u_decoder (
    .inst      (inst),
    .alu_op    (alu_op),
    .alu_a_sel (alu_a_sel),
    .alu_b_sel (alu_b_sel),
    .imm_sel   (imm_sel),
    .reg_write (reg_write),
    .wb_sel    (wb_sel),
    .mem_read  (mem_read),
    .mem_write (mem_write),
    .mem_op    (mem_op),
    .branch    (branch),
    .jump      (jump),
    .jalr      (jalr),
    .ecall     (ecall),
    .ebreak    (ebreak),
    .illegal   (illegal)
  );

  imm_gen u_imm_gen (
    .inst    (inst),
    .imm_sel (imm_sel),
    .imm     (imm)
  );

  // ---------------------------------------------------------------------------
  // Registers. Writes stop once halted, and a trapping instruction writes
  // nothing, so a faulting instruction leaves no trace.
  // ---------------------------------------------------------------------------
  regfile u_regfile (
    .clk      (clk),
    .rst      (rst),
    .rs1_addr (inst[19:15]),
    .rs2_addr (inst[24:20]),
    .rs1_data (rs1_data),
    .rs2_data (rs2_data),
    .we       (reg_write && !halted && !trap && step_en),
    .rd_addr  (inst[11:7]),
    .rd_data  (wb_data)
  );

  // ---------------------------------------------------------------------------
  // Execute
  // ---------------------------------------------------------------------------
  always_comb begin
    case (alu_a_sel)
      ALU_A_PC:   alu_a = pc;
      ALU_A_ZERO: alu_a = 32'b0;
      default:    alu_a = rs1_data;
    endcase
  end

  assign alu_b = (alu_b_sel == ALU_B_IMM) ? imm : rs2_data;

  alu u_alu (
    .a  (alu_a),
    .b  (alu_b),
    .op (alu_op),
    .y  (alu_y)
  );

  branch_cmp u_branch_cmp (
    .a      (rs1_data),
    .b      (rs2_data),
    .funct3 (inst[14:12]),
    .taken  (taken)
  );

  // ---------------------------------------------------------------------------
  // Data memory. d_read/d_write are gated by `halted` only, never by `trap`:
  // trap depends on d_misaligned, which depends on these, so gating on it would
  // close a combinational loop. The memory refuses misaligned stores itself.
  // ---------------------------------------------------------------------------
  assign d_addr  = alu_y;
  assign d_op    = mem_op;
  assign d_read  = mem_read  && !halted;
  assign d_write = mem_write && !halted && step_en;
  assign d_wdata = rs2_data;

  always_comb begin
    case (wb_sel)
      WB_MEM:  wb_data = d_rdata;
      WB_PC4:  wb_data = pc_plus4;
      default: wb_data = alu_y;
    endcase
  end

  // ---------------------------------------------------------------------------
  // Traps
  // ---------------------------------------------------------------------------
  always_comb begin
    if      (illegal)                                 trap_cause = HALT_ILLEGAL;
    else if (ecall)                                   trap_cause = HALT_ECALL;
    else if (ebreak)                                  trap_cause = HALT_EBREAK;
    else if ((mem_read || mem_write) && d_misaligned) trap_cause = HALT_MEM_MISALIGN;
    else if (misaligned_target)                       trap_cause = HALT_FETCH_MISALIGN;
    else                                              trap_cause = HALT_NONE;
  end

  assign trap = (trap_cause != HALT_NONE) && !halted;

  always_ff @(posedge clk) begin
    if (rst) begin
      halted     <= 1'b0;
      halt_cause <= HALT_NONE;
    end else if (trap && step_en) begin
      halted     <= 1'b1;
      halt_cause <= trap_cause;
    end
  end

  // ---------------------------------------------------------------------------
  // Next PC
  // ---------------------------------------------------------------------------
  pc_unit u_pc_unit (
    .clk               (clk),
    .rst               (rst),
    .stall             (halted || trap || !step_en),
    .branch            (branch),
    .taken             (taken),
    .jump              (jump),
    .jalr              (jalr),
    .imm               (imm),
    .alu_result        (alu_y),
    .pc                (pc),
    .pc_plus4          (pc_plus4),
    .pc_next           (pc_next),
    .misaligned_target (misaligned_target)
  );

  // ---------------------------------------------------------------------------
  // Retirement trace
  // ---------------------------------------------------------------------------
  assign commit_valid     = !halted && !trap && !rst && step_en;
  assign commit_pc        = pc;
  assign commit_inst      = inst;
  assign commit_next_pc   = pc_next;
  assign commit_rd        = reg_write ? inst[11:7] : 5'd0;
  assign commit_rd_wdata  = (reg_write && inst[11:7] != 5'd0) ? wb_data : 32'b0;
  assign commit_mem_write = d_write && !d_misaligned;
  assign commit_mem_addr  = d_addr;
  assign commit_mem_wdata = d_wdata;

endmodule
