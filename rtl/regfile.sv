// regfile.sv
// 32 x 32-bit register file: two combinational read ports, one synchronous
// write port. x0 is hardwired to zero. Registers reset to zero so the core
// starts from the same architectural state as the golden model.

module regfile (
  input  logic        clk,
  input  logic        rst,

  input  logic [4:0]  rs1_addr,
  input  logic [4:0]  rs2_addr,
  output logic [31:0] rs1_data,
  output logic [31:0] rs2_data,

  input  logic        we,
  input  logic [4:0]  rd_addr,
  input  logic [31:0] rd_data
);

  logic [31:0] regs [0:31];

  always_ff @(posedge clk) begin
    if (rst) begin
      for (int i = 0; i < 32; i++) regs[i] <= 32'b0;
    end else if (we && rd_addr != 5'd0) begin
      regs[rd_addr] <= rd_data;
    end
  end

  assign rs1_data = (rs1_addr == 5'd0) ? 32'b0 : regs[rs1_addr];
  assign rs2_data = (rs2_addr == 5'd0) ? 32'b0 : regs[rs2_addr];

endmodule
