// =============================================================================
// HY-RV | fetch_ctrl
// Description: Fetch offer, redirect, drain, restart, and fault-barrier control.
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

// Owns boot/restart, irrevocable held offers, quiesce and the single fault barrier.
module fetch_ctrl (
    input logic clk,rst_n,redirect_i,drain_req_i,backend_idle_i,
    input logic pending_i,held_response_empty_i,
    input logic req_valid_i,req_ready_i,accepted_i,
    input logic fresh_fault_visible_i,alloc_fault_i,
    input logic [31:0] redirect_pc_i,resume_pc_i,req_pc_i,
    input rv_bp_pkg::bp_lookup_t lookup_i,
    output logic boot_pending_o,redirect_pending_o,held_o,held_stale_o,
    output logic [31:0] redirect_pc_o,held_pc_o,
    output rv_bp_pkg::bp_lookup_t held_lookup_o,
    output logic run_o,kill_o,fault_barrier_o,stopped_o
);
    typedef enum logic [1:0] {RUN,STOPPING,STOPPED,RESTART} run_state_t;
    run_state_t state_q;
    assign run_o=state_q==RUN;
    assign kill_o=redirect_i||drain_req_i||state_q!=RUN;
    assign stopped_o=state_q==STOPPED;
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            boot_pending_o<=1;redirect_pending_o<=0;redirect_pc_o<=0;
            held_o<=0;held_stale_o<=0;held_pc_o<=0;held_lookup_o<='0;
            state_q<=RUN;fault_barrier_o<=0;
        end else begin
            if (req_valid_i&&!req_ready_i&&!held_o) begin
                held_o<=1;held_pc_o<=req_pc_i;held_lookup_o<=lookup_i;held_stale_o<=kill_o;
            end
            if (accepted_i) begin
                held_o<=0;held_stale_o<=0;
                if (!held_stale_o&&!kill_o) begin boot_pending_o<=0;redirect_pending_o<=0;end
            end
            if (kill_o) begin
                fault_barrier_o<=0;
                if (held_o&&!accepted_i) held_stale_o<=1;
            end else if (fresh_fault_visible_i||alloc_fault_i) fault_barrier_o<=1;
            case (state_q)
                RUN: if (drain_req_i) state_q<=STOPPING;
                STOPPING: if (backend_idle_i&&!pending_i&&!held_o&&!req_valid_i&&held_response_empty_i) state_q<=STOPPED;
                STOPPED: if (!drain_req_i) state_q<=RESTART;
                RESTART: begin
                    redirect_pending_o<=1;redirect_pc_o<=resume_pc_i;boot_pending_o<=0;
                    state_q<=drain_req_i?STOPPING:RUN;
                end
            endcase
            if (redirect_i) begin redirect_pending_o<=1;redirect_pc_o<=redirect_pc_i;end
        end
    end
endmodule
