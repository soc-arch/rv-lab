// =============================================================================
// HY-RV | gen_pc_nxt
// Description: Stateless next-fetch-address policy.
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

// Stateless fetch-address policy. Control owns boot, restart and held-offer state.
module gen_pc_nxt (
    input  logic [31:0] pc_q_i,
    input  logic        advance_i,
    input  logic [31:0] seq_step_i,
    input  logic        boot_pending_i,
    input  logic [31:0] boot_pc_i,
    input  logic        redirect_valid_i,
    input  logic [31:0] redirect_pc_i,
    input  logic        pred_valid_i,
    input  logic [31:0] pred_target_i,
    input  logic        held_valid_i,
    input  logic [31:0] held_pc_i,
    output logic [31:0] pc_nxt
);
    always_comb begin
        pc_nxt = pc_q_i;
        if      (held_valid_i)     pc_nxt = held_pc_i;
        else if (redirect_valid_i) pc_nxt = redirect_pc_i;
        else if (boot_pending_i)   pc_nxt = boot_pc_i;
        else if (advance_i && pred_valid_i) pc_nxt = pred_target_i;
        else if (advance_i)        pc_nxt = pc_q_i + seq_step_i;
    end
endmodule
