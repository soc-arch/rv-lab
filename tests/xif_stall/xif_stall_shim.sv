// =============================================================================
// HY-RV | xif_stall_shim
// Description: Verification-only XIF-lite shim that randomly stalls the issue and result channels.
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

// Used only by `make lab10-check` / `ext-test EXT=xacc` in a build copy of the
// Lab 10 CPU (never in student/). A blocking core never meets a busy coprocessor
// and is always ready for a result, so without this shim the core's issue-stall
// path and a late result are never exercised. The shim withholds issue_ready and
// result_valid on pseudo-random cycles; payloads pass straight through.
module xif_stall_shim #(
    parameter logic [31:0] SEED = 32'h1D2C_3B4A
) (
    input logic clk,
    input logic rst_n,
    xif_lite_if.coproc core_side,   // faces the core
    xif_lite_if.core   cp_side      // faces the coprocessor
);
    logic [31:0] lfsr;
    logic issue_stall, result_stall;
    always_ff @(posedge clk or negedge rst_n)
        if (!rst_n) lfsr <= SEED;
        else        lfsr <= {lfsr[30:0], lfsr[31] ^ lfsr[21] ^ lfsr[1] ^ lfsr[0]};
    assign issue_stall  = lfsr[2:0] < 3'd5;   // about 5 of 8 cycles
    assign result_stall = lfsr[6:4] < 3'd4;   // about 4 of 8 cycles

    assign cp_side.issue_valid       = core_side.issue_valid && !issue_stall;
    assign cp_side.issue_insn        = core_side.issue_insn;
    assign cp_side.issue_pc          = core_side.issue_pc;
    assign cp_side.issue_rs1         = core_side.issue_rs1;
    assign cp_side.issue_rs2         = core_side.issue_rs2;
    assign core_side.issue_ready     = cp_side.issue_ready && !issue_stall;
    assign core_side.issue_accept    = cp_side.issue_accept;
    assign core_side.issue_writeback = cp_side.issue_writeback;

    assign core_side.result_valid    = cp_side.result_valid && !result_stall;
    assign core_side.result_data     = cp_side.result_data;
    assign core_side.result_we       = cp_side.result_we;
    assign cp_side.result_ready      = core_side.result_ready && !result_stall;

    // synthesis translate_off
    longint unsigned issue_stall_cycles = 0, result_stall_cycles = 0, issues = 0, results = 0;
    logic        held_result = 0;      // previous cycle: coprocessor result offered, not taken
    logic [31:0] held_data;
    logic        held_we;
    always @(posedge clk) begin
        if (!rst_n) held_result <= 0;
        else begin
            if (core_side.issue_valid && !core_side.issue_ready) issue_stall_cycles++;
            if (cp_side.result_valid && !core_side.result_valid) result_stall_cycles++;
            if (core_side.issue_valid && core_side.issue_ready && core_side.issue_accept) issues++;
            if (core_side.result_valid && core_side.result_ready) results++;
            // A result that was not taken must still be offered, unchanged.
            if (held_result)
                assert (cp_side.result_valid && cp_side.result_data == held_data && cp_side.result_we == held_we)
                    else $fatal(1, "xif_stall_shim: coprocessor withdrew or changed a held result");
            held_result <= cp_side.result_valid && !cp_side.result_ready;
            held_data   <= cp_side.result_data;
            held_we     <= cp_side.result_we;
        end
    end
    final $display("[XIF-STALL] issue_stall_cycles=%0d result_stall_cycles=%0d accepted=%0d results=%0d",
                   issue_stall_cycles, result_stall_cycles, issues, results);
    // synthesis translate_on
endmodule
