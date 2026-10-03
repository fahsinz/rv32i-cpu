// top.sv  --  DE10-Lite (MAX 10, 10M50DAF484C7G)
//
// First hardware target: the ALU driven by the slide switches, result shown on
// the 7-segment displays and the red LEDs. Purely combinational, so there is no
// clock and nothing for timing analysis to close yet. The point is to prove the
// synthesis -> fit -> pin-assignment -> program flow on the real board with a
// block that is already verified in simulation.
//
// SW[3:0] = operand a      SW[7:4] = operand b      SW[9:8] = operation
//   00 ADD   01 SUB   10 AND   11 SLT
// HEX1,HEX0 = result low byte in hex, LEDR = result low 10 bits.

module top (
  input  logic [9:0] SW,
  output logic [9:0] LEDR,
  output logic [7:0] HEX0,
  output logic [7:0] HEX1
);

  // Active-low segments, bit order [7]=DP, [6]=G ... [0]=A.
  function automatic logic [7:0] seg7(input logic [3:0] v);
    case (v)
      4'h0: seg7 = 8'hC0;
      4'h1: seg7 = 8'hF9;
      4'h2: seg7 = 8'hA4;
      4'h3: seg7 = 8'hB0;
      4'h4: seg7 = 8'h99;
      4'h5: seg7 = 8'h92;
      4'h6: seg7 = 8'h82;
      4'h7: seg7 = 8'hF8;
      4'h8: seg7 = 8'h80;
      4'h9: seg7 = 8'h90;
      4'hA: seg7 = 8'h88;
      4'hB: seg7 = 8'h83;
      4'hC: seg7 = 8'hC6;
      4'hD: seg7 = 8'hA1;
      4'hE: seg7 = 8'h86;
      4'hF: seg7 = 8'h8E;
    endcase
  endfunction

  logic [3:0]  op;
  logic [31:0] y;

  always_comb begin
    case (SW[9:8])
      2'd0:    op = rv32i_pkg::ALU_ADD;
      2'd1:    op = rv32i_pkg::ALU_SUB;
      2'd2:    op = rv32i_pkg::ALU_AND;
      default: op = rv32i_pkg::ALU_SLT;
    endcase
  end

  alu u_alu (
    .a  ({28'b0, SW[3:0]}),
    .b  ({28'b0, SW[7:4]}),
    .op (op),
    .y  (y)
  );

  assign LEDR = y[9:0];
  assign HEX0 = seg7(y[3:0]);
  assign HEX1 = seg7(y[7:4]);

endmodule
