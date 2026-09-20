// memory.sv
// Unified byte-addressed memory: one read-only instruction port, one data port
// with sub-word loads and stores. Storage is word-wide; narrow accesses pick a
// lane from the addressed word, which is how a real SRAM with byte enables
// behaves.
//
// Addresses wrap within the array (only the low index bits are used), so a
// runaway program cannot read outside the model.

module memory #(
  parameter int unsigned WORDS     = 4096,  // must be a power of two
  parameter string       INIT_FILE = ""
) (
  input  logic        clk,

  // Instruction port: combinational, word aligned
  input  logic [31:0] i_addr,
  output logic [31:0] i_rdata,

  // Data port
  input  logic [31:0] d_addr,
  input  logic [2:0]  d_op,      // funct3 of the load/store
  input  logic        d_read,
  input  logic        d_write,
  input  logic [31:0] d_wdata,
  output logic [31:0] d_rdata,
  output logic        d_misaligned
);

  localparam int IDX_BITS = $clog2(WORDS);

  logic [31:0] mem [0:WORDS-1];

  initial begin
    for (int i = 0; i < WORDS; i++) mem[i] = 32'b0;
    if (INIT_FILE != "") $readmemh(INIT_FILE, mem);
  end

  logic [IDX_BITS-1:0] i_index, d_index;
  assign i_index = i_addr[IDX_BITS+1:2];
  assign d_index = d_addr[IDX_BITS+1:2];

  assign i_rdata = mem[i_index];

  // ---------------------------------------------------------------------------
  // Alignment: halfwords need bit 0 clear, words need bits [1:0] clear
  // ---------------------------------------------------------------------------
  logic unaligned;
  always_comb begin
    case (d_op)
      3'b001, 3'b101: unaligned = d_addr[0];        // LH / LHU / SH
      3'b010:         unaligned = |d_addr[1:0];     // LW / SW
      default:        unaligned = 1'b0;             // bytes are always aligned
    endcase
  end
  assign d_misaligned = (d_read || d_write) && unaligned;

  // ---------------------------------------------------------------------------
  // Load path: select the lane, then sign- or zero-extend
  // ---------------------------------------------------------------------------
  logic [31:0] word;
  logic [1:0]  off;
  logic [7:0]  lane_b;
  logic [15:0] lane_h;

  assign word = mem[d_index];
  assign off  = d_addr[1:0];

  always_comb begin
    case (off)
      2'd0:    lane_b = word[7:0];
      2'd1:    lane_b = word[15:8];
      2'd2:    lane_b = word[23:16];
      default: lane_b = word[31:24];
    endcase
    lane_h = off[1] ? word[31:16] : word[15:0];

    case (d_op)
      3'b000:  d_rdata = {{24{lane_b[7]}}, lane_b};  // LB
      3'b001:  d_rdata = {{16{lane_h[15]}}, lane_h}; // LH
      3'b010:  d_rdata = word;                       // LW
      3'b100:  d_rdata = {24'b0, lane_b};            // LBU
      3'b101:  d_rdata = {16'b0, lane_h};            // LHU
      default: d_rdata = word;
    endcase
  end

  // ---------------------------------------------------------------------------
  // Store path: replicate the data across lanes, then merge under byte enables
  // ---------------------------------------------------------------------------
  logic [3:0]  byte_en;
  logic [31:0] wdata_lanes, merged;

  always_comb begin
    case (d_op)
      3'b000:  byte_en = 4'b0001 << off;                  // SB
      3'b001:  byte_en = off[1] ? 4'b1100 : 4'b0011;      // SH
      default: byte_en = 4'b1111;                         // SW
    endcase

    case (d_op)
      3'b000:  wdata_lanes = {4{d_wdata[7:0]}};
      3'b001:  wdata_lanes = {2{d_wdata[15:0]}};
      default: wdata_lanes = d_wdata;
    endcase

    merged = word;
    if (byte_en[0]) merged[7:0]   = wdata_lanes[7:0];
    if (byte_en[1]) merged[15:8]  = wdata_lanes[15:8];
    if (byte_en[2]) merged[23:16] = wdata_lanes[23:16];
    if (byte_en[3]) merged[31:24] = wdata_lanes[31:24];
  end

  always_ff @(posedge clk) begin
    if (d_write && !d_misaligned) mem[d_index] <= merged;
  end

endmodule
