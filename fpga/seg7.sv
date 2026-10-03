// seg7.sv -- one hex digit on a DE10-Lite 7-segment display.
// Segments are active low; bit order is [7]=decimal point, [6]=G ... [0]=A.

module seg7 (
  input  logic [3:0] value,
  output logic [7:0] segments
);

  always_comb begin
    case (value)
      4'h0:    segments = 8'hC0;
      4'h1:    segments = 8'hF9;
      4'h2:    segments = 8'hA4;
      4'h3:    segments = 8'hB0;
      4'h4:    segments = 8'h99;
      4'h5:    segments = 8'h92;
      4'h6:    segments = 8'h82;
      4'h7:    segments = 8'hF8;
      4'h8:    segments = 8'h80;
      4'h9:    segments = 8'h90;
      4'hA:    segments = 8'h88;
      4'hB:    segments = 8'h83;
      4'hC:    segments = 8'hC6;
      4'hD:    segments = 8'hA1;
      4'hE:    segments = 8'h86;
      default: segments = 8'h8E;
    endcase
  end

endmodule
