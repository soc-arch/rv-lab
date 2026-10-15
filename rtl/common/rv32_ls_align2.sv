// =============================================================================
// HY-RV | rv32_ls_align2
// Description: Align load/store data and byte enables across memory words.
//
// Purpose: Computer architecture and RTL design education and lab exercises.
// Maintained by: DSAL (Digital System Architecture Lab), Hanyang University
// Website: https://dsa.hanyang.ac.kr
// Supervisor: Prof. Ji-Hoon Kim (jhoonkim@hanyang.ac.kr)
//
// AI tools such as Codex or Claude may have assisted in creating or modifying
// this file. See the applicable manifests and verification records for
// file-specific provenance, revision history, and validation evidence.
// Preserve existing license, copyright, and original author notices.
// =============================================================================

// Local editable teaching snapshot; see SOURCE_SNAPSHOT.json for provenance.
// =============================================================================
// rv32_ls_align2 — 2-word load aligner with misalign-spanning support
//

// a 4-byte word boundary.  Inputs are TWO sequential 32-bit words read from
// memory (first at addr & ~0x3, second at (addr & ~0x3) + 4).
//
// Semantics:
//   concat    = {second_word, first_word}   // 64 bits
//   shifted   = concat >> (addr_lo * 8)     // byte-shift to lane 0
//   aligned   = sign/zero-extend of shifted[size-1:0] per funct3
//
// The caller is responsible for issuing the second access only when span=1
// (== addr_lo + access_size > 4).  rv32_ls_split exports the span signal.
//
// funct3 codes (RV32I):
//   000 LB  — 1B, sign-ext
//   001 LH  — 2B, sign-ext
//   010 LW  — 4B
//   100 LBU — 1B, zero-ext
//   101 LHU — 2B, zero-ext
// =============================================================================

module rv32_ls_align2 (
    input  logic [31:0] first_word,
    input  logic [31:0] second_word,
    input  logic [1:0]  addr_lo,
    input  logic [2:0]  funct3,
    output logic [31:0] aligned_data
);

    logic [63:0] concat;
    logic [63:0] shifted;
    logic [5:0]  shift_bits;

    assign concat     = {second_word, first_word};
    assign shift_bits = {1'b0, addr_lo, 3'b000};   // addr_lo * 8
    assign shifted    = concat >> shift_bits;

    // Extract size-appropriate field and extend.
    always_comb begin
        unique case (funct3)
            3'b000:  aligned_data = {{24{shifted[7]}},  shifted[ 7:0]};    // LB
            3'b001:  aligned_data = {{16{shifted[15]}}, shifted[15:0]};    // LH
            3'b010:  aligned_data = shifted[31:0];                         // LW
            3'b100:  aligned_data = {24'b0, shifted[ 7:0]};                // LBU
            3'b101:  aligned_data = {16'b0, shifted[15:0]};                // LHU
            default: aligned_data = shifted[31:0];                         // passthrough (LD/LWU — n/a RV32)
        endcase
    end

endmodule
