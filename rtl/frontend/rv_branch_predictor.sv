// =============================================================================
// HY-RV | rv_branch_predictor
// Description: Static BP0/BP1 lookup, refinement, and completion-feedback boundary.
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

// Static BP0/BP1 sibling boundary. Lookup/update/maintenance have no state.
module rv_branch_predictor #(
    parameter int unsigned BP_PROFILE=0, COND_POLICY=0,
    parameter bit EARLY_JAL_EN=0, STATIC_POLICY_EN=1
) (
    input logic clk, rst_n,
    input logic lookup_valid_i,
    input logic [31:0] lookup_pc_i,
    output rv_bp_pkg::bp_lookup_t lookup_record_o,
    input logic refine_valid_i,
    input logic [31:0] refine_pc_i,
    input rv_bp_pkg::bp_predecode_t predecode_i,
    input rv_bp_pkg::bp_lookup_t saved_lookup_i,
    output rv_bp_pkg::bp_prediction_t effective_o,
    input logic update_valid_i,
    input rv_bp_pkg::bp_update_t update_i,
    input logic invalidate_frontend_state_i
);
    initial begin
        if (BP_PROFILE>1 || COND_POLICY>1 || BP_PROFILE!=COND_POLICY)
            $fatal(1,"Static BP profile/policy mismatch: BP0=ANT, BP1=BTFNT");
    end
    assign lookup_record_o='0;
    rv_bp_policy #(.COND_POLICY(COND_POLICY),.EARLY_JAL_EN(EARLY_JAL_EN),.STATIC_POLICY_EN(STATIC_POLICY_EN)) u_policy (
        .valid_i(refine_valid_i),.pc_i(refine_pc_i),.saved_lookup_i,.predecode_i,.prediction_o(effective_o)
    );
endmodule
