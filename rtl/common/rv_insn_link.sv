// =============================================================================
// HY-RV | rv_insn_link
// Description: Queue-depth-zero instruction token forwarding and flush gating.
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

// Independent F/P connection. Positive-depth storage is a later, separate step.
module rv_insn_link #(parameter int unsigned INSN_QUEUE_DEPTH=0) (
    input logic rst_n, flush_i,
    insn_supply_if.token_sink f_if,
    insn_supply_if.token_source p_if
);
    if (INSN_QUEUE_DEPTH == 0) begin : g_direct
        assign p_if.valid = rst_n && !flush_i && f_if.valid;
        assign f_if.ready = rst_n && !flush_i && p_if.ready;
        assign p_if.pc = f_if.pc;
        assign p_if.insn = f_if.insn;
        assign p_if.fault = f_if.fault;
        assign p_if.fault_misaligned = f_if.fault_misaligned;
        assign p_if.predicted_taken = f_if.predicted_taken;
        assign p_if.predicted_target = f_if.predicted_target;
        assign p_if.predicted_ghr_snapshot = f_if.predicted_ghr_snapshot;
        assign p_if.prediction = f_if.prediction;
        assign p_if.bp_meta = f_if.bp_meta;
    end else begin : g_unsupported_depth
        initial $fatal(1, "rv_insn_link currently supports INSN_QUEUE_DEPTH=0 only");
        assign p_if.valid = 1'b0;
        assign f_if.ready = 1'b0;
        assign p_if.pc = '0;
        assign p_if.insn = '0;
        assign p_if.fault = 1'b0;
        assign p_if.fault_misaligned = 1'b0;
        assign p_if.predicted_taken = 1'b0;
        assign p_if.predicted_target = '0;
        assign p_if.predicted_ghr_snapshot = '0;
        assign p_if.prediction = '0;
        assign p_if.bp_meta = '0;
    end
endmodule
