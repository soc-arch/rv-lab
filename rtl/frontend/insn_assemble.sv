// =============================================================================
// HY-RV | insn_assemble
// Description: Assemble producer-held instruction responses into tokens.
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

// Memory producer holds bytes; only a bus-free local fault has a PRESENT slot.
module insn_assemble (
    input logic clk,rst_n,kill_i,fresh_i,alloc_fault_i,
    input logic [31:0] owner_pc_i,response_insn_i,selected_pc_i,
    input logic response_error_i,
    input rv_bp_pkg::bp_lookup_t lookup_i,
    input rv_bp_pkg::bp_prediction_t prediction_i,
    output logic local_fault_present_o,
    insn_supply_if.token_source insn_if
);
    logic [31:0] local_fault_pc_q;
    wire fault=local_fault_present_o||response_error_i;
    assign insn_if.valid=rst_n&&!kill_i&&(local_fault_present_o||fresh_i);
    assign insn_if.pc=local_fault_present_o?local_fault_pc_q:owner_pc_i;
    assign insn_if.insn=fault?32'h13:response_insn_i;
    assign insn_if.fault=fault;
    assign insn_if.fault_misaligned=local_fault_present_o;
    assign insn_if.prediction=fault ?
        rv_bp_pkg::bp_prediction_t'({1'b0,insn_if.pc+32'd4,4'b0,4'b0}) : prediction_i;
    assign insn_if.bp_meta=fault?'0:lookup_i;
    assign insn_if.predicted_taken=insn_if.prediction.taken;
    assign insn_if.predicted_target=insn_if.prediction.taken?insn_if.prediction.next_pc:32'b0;
    assign insn_if.predicted_ghr_snapshot=0;
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin local_fault_present_o<=0;local_fault_pc_q<=0;end
        else if (kill_i) local_fault_present_o<=0;
        else begin
            if (local_fault_present_o&&insn_if.valid&&insn_if.ready) local_fault_present_o<=0;
            if (alloc_fault_i) begin local_fault_present_o<=1;local_fault_pc_q<=selected_pc_i;end
        end
    end
endmodule
