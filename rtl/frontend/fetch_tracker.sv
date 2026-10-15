// =============================================================================
// HY-RV | fetch_tracker
// Description: Track the single accepted fetch descriptor and response ownership.
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

// One accepted descriptor. Payload persists after response completion.
module fetch_tracker (
    input logic clk,rst_n,kill_i,response_i,accepted_i,req_stale_i,f_fire_i,
    input logic [31:0] req_pc_i,
    input rv_bp_pkg::bp_lookup_t req_lookup_i,
    input rv_bp_pkg::bp_prediction_t effective_i,
    output logic [31:0] owner_pc_o,
    output logic pending_o,stale_o,
    output rv_bp_pkg::bp_lookup_t owner_lookup_o,
    output rv_bp_pkg::bp_prediction_t owner_prediction_o
);
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin owner_pc_o<=0;pending_o<=0;stale_o<=0;owner_lookup_o<='0;owner_prediction_o<='0;end
        else begin
            if (response_i) begin pending_o<=0;stale_o<=0;end
            if (f_fire_i) owner_prediction_o<=effective_i;
            if (kill_i&&pending_o&&!response_i) stale_o<=1;
            // Allocation wins over old owner completion at the same edge.
            if (accepted_i) begin
                pending_o<=1;owner_pc_o<=req_pc_i;owner_lookup_o<=req_lookup_i;
                owner_prediction_o<='{taken:1'b0,next_pc:req_pc_i+32'd4,source:4'b0,refine_flags:4'b0};
                stale_o<=req_stale_i||kill_i;
            end
        end
    end
endmodule
