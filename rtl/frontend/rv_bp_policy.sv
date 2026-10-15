// =============================================================================
// HY-RV | rv_bp_policy
// Description: Combinational ANT/BTFNT policy and independent early JAL option.
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

module rv_bp_policy #(
    parameter int unsigned COND_POLICY=0,
    parameter bit EARLY_JAL_EN=0,
    parameter bit STATIC_POLICY_EN=1
) (
    input logic valid_i,
    input logic [31:0] pc_i,
    input rv_bp_pkg::bp_lookup_t saved_lookup_i,
    input rv_bp_pkg::bp_predecode_t predecode_i,
    output rv_bp_pkg::bp_prediction_t prediction_o
);
    import rv_bp_pkg::*;
    logic choose_taken;
    always_comb begin
        prediction_o='0;
        prediction_o.next_pc=pc_i+32'd4;
        choose_taken=valid_i && STATIC_POLICY_EN && predecode_i.direct_target_valid &&
            ((predecode_i.kind==CFI_COND && COND_POLICY==1 && predecode_i.offset_negative) ||
             (predecode_i.kind==CFI_JAL && EARLY_JAL_EN));
        if (choose_taken) begin
            if (predecode_i.target_aligned) begin
                prediction_o.taken=1;
                prediction_o.next_pc=predecode_i.direct_target;
                prediction_o.source=predecode_i.kind==CFI_JAL ? BP_EARLY_JAL : BP_BTFNT;
                prediction_o.refine_flags[0]=1;
            end else prediction_o.refine_flags[3]=1;
        end
    end
endmodule
