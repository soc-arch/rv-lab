// Local editable teaching snapshot; see SOURCE_SNAPSHOT.json for provenance.
// =============================================================================
// rv32_ls_split — LD/ST misalign splitter (byte-enable + wdata for 2 accesses)
//

// Produces byte-enable + replicated wdata for BOTH the first access (at
// word-aligned base) and the optional second access (at base + 4).
// `span` is asserted when the access crosses a 4-byte word boundary and
// the caller must issue a second dmem transaction.
//
// Byte-enable formula:
//   bytes_in_access = {1, 2, 4} for {SB/LB, SH/LH, SW/LW}
//   mask8           = ((1 << bytes_in_access) - 1) << addr_lo   // 8-bit mask
//   first_be  = mask8[3:0]
//   second_be = mask8[7:4]
//   span      = |second_be
//
// Wdata formula (stores):
//   wide64            = {32'b0, rs2_data} << (addr_lo * 8)
//   first_wdata       = wide64[31:0]
//   second_wdata      = wide64[63:32]
//
// For loads: first_be/second_be are driven the same way (SRAM reads whole
// word but the caller only consumes bytes in the masked lanes).  Wdata
// outputs are unused for loads (dmem req_we=0).
// =============================================================================

module rv32_ls_split (
    input  logic [31:0] rs2_data,
    input  logic [1:0]  addr_lo,
    input  logic [2:0]  funct3,      // funct3[1:0]: 00=byte, 01=half, 10=word

    output logic        span,        // 1 = need second access at base+4
    output logic [3:0]  first_be,
    output logic [3:0]  second_be,
    output logic [31:0] first_wdata,
    output logic [31:0] second_wdata
);

    logic [2:0] bytes_in_access;   // 1, 2, or 4
    logic [7:0] all_bytes_mask;    // ((1<<N)-1) << addr_lo
    logic [5:0] shift_bits;        // addr_lo * 8

    always_comb begin
        unique case (funct3[1:0])
            2'b00:   bytes_in_access = 3'd1;    // SB/LB/LBU
            2'b01:   bytes_in_access = 3'd2;    // SH/LH/LHU
            default: bytes_in_access = 3'd4;    // SW/LW
        endcase
    end

    // Build base byte-mask ((1<<N)-1 for N in {1,2,4}) and shift by addr_lo.
    logic [3:0] base_mask4;
    always_comb begin
        unique case (bytes_in_access)
            3'd1:    base_mask4 = 4'b0001;
            3'd2:    base_mask4 = 4'b0011;
            default: base_mask4 = 4'b1111;       // SW: all 4
        endcase
    end

    // 8-bit shifted mask: bits 0..7 cover up to 2 word lanes.
    assign all_bytes_mask = {4'b0, base_mask4} << addr_lo;

    assign first_be  = all_bytes_mask[3:0];
    assign second_be = all_bytes_mask[7:4];
    assign span      = |second_be;

    // Wdata shift.
    assign shift_bits = {1'b0, addr_lo, 3'b000};
    logic [63:0] wide64;
    assign wide64 = {32'b0, rs2_data} << shift_bits;

    assign first_wdata  = wide64[31:0];
    assign second_wdata = wide64[63:32];

endmodule
