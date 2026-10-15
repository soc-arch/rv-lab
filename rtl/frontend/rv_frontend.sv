// =============================================================================
// HY-RV | rv_frontend
// Description: F0 instruction supply with one owner and no separate response buffer.
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

// F0: one owner, no instruction response buffer, producer-held response.
module rv_frontend #(
    parameter logic [31:0] RESET_PC=32'h8000_0000
) (
    input logic clk,rst_n,drain_req_i,redirect_i,
    input logic [31:0] redirect_pc_i,resume_pc_i,
    input logic backend_idle_i,
    output logic idle_o,stopped_o,kill_o,
    output logic lookup_valid_o,
    output logic [31:0] lookup_pc_o,refine_pc_o,
    input rv_bp_pkg::bp_lookup_t lookup_record_i,
    output logic refine_valid_o,
    output rv_bp_pkg::bp_predecode_t predecode_o,
    output rv_bp_pkg::bp_lookup_t saved_lookup_o,
    input rv_bp_pkg::bp_prediction_t effective_i,
    mem_if.master imem_if,
    insn_supply_if.token_source insn_if
);
    logic [31:0] owner_pc,held_pc,pc_nxt,redirect_pc;
    logic boot_pending,redirect_pending,pending,stale,held,held_stale,local_fault;
    logic run,fault_barrier;
    rv_bp_pkg::bp_lookup_t held_lookup,owner_lookup;
    rv_bp_pkg::bp_prediction_t owner_prediction;
    wire response=pending&&imem_if.resp_valid&&imem_if.resp_ready;
    wire fresh=pending&&imem_if.resp_valid&&!stale&&!kill_o;
    wire f_fire=insn_if.valid&&insn_if.ready;
    wire accepted=imem_if.req_valid&&imem_if.req_ready;
    wire fresh_fault=fresh&&imem_if.resp_error;
    // A successor offer is permitted at A f_fire. The frozen C1 memory
    // adapter declines it until the next edge; C2 enables memory replacement.
    wire available=!pending||response;
    wire can_start=run&&!kill_o&&!held&&available&&!fault_barrier&&!fresh_fault&&!local_fault;
    wire alloc_fault=can_start&&pc_nxt[1:0]!=0;
    gen_pc_nxt u_gen_pc_nxt (
        .pc_q_i(owner_pc),.advance_i(1'b1),.seq_step_i(32'd4),
        .boot_pending_i(boot_pending),.boot_pc_i(RESET_PC),
        .redirect_valid_i(redirect_pending),.redirect_pc_i(redirect_pc),
        .pred_valid_i(1'b1),.pred_target_i(f_fire?effective_i.next_pc:owner_prediction.next_pc),
        .held_valid_i(held),.held_pc_i(held_pc),.pc_nxt
    );
    fetch_ctrl u_fetch_ctrl (
        .clk,.rst_n,.redirect_i,.redirect_pc_i,.drain_req_i,.backend_idle_i,.resume_pc_i,
        .pending_i(pending),.held_response_empty_i(!local_fault),
        .req_valid_i(imem_if.req_valid),.req_ready_i(imem_if.req_ready),
        .accepted_i(accepted),.req_pc_i(pc_nxt),.lookup_i(lookup_record_i),
        .fresh_fault_visible_i(fresh_fault),.alloc_fault_i(alloc_fault),
        .boot_pending_o(boot_pending),.redirect_pending_o(redirect_pending),.held_o(held),.held_stale_o(held_stale),
        .redirect_pc_o(redirect_pc),.held_pc_o(held_pc),.held_lookup_o(held_lookup),
        .run_o(run),.kill_o,.fault_barrier_o(fault_barrier),.stopped_o
    );
    fetch_tracker u_fetch_tracker (
        .clk,.rst_n,.kill_i(kill_o),.response_i(response),.accepted_i(accepted),.req_stale_i(held_stale),
        .f_fire_i(f_fire),.effective_i(insn_if.prediction),.req_pc_i(pc_nxt),.req_lookup_i(held?held_lookup:lookup_record_i),
        .owner_pc_o(owner_pc),.pending_o(pending),.stale_o(stale),.owner_lookup_o(owner_lookup),.owner_prediction_o(owner_prediction)
    );
    rv_branch_predecode u_branch_predecode (
        .valid_i(refine_valid_o),.pc_i(owner_pc),.insn_i(imem_if.resp_rdata),.predecode_o
    );
    insn_assemble u_insn_assemble (
        .clk,.rst_n,.kill_i(kill_o),.fresh_i(fresh),.alloc_fault_i(alloc_fault),
        .owner_pc_i(owner_pc),.response_insn_i(imem_if.resp_rdata),.selected_pc_i(pc_nxt),
        .response_error_i(imem_if.resp_error),.lookup_i(owner_lookup),.prediction_i(effective_i),
        .local_fault_present_o(local_fault),.insn_if
    );
    assign lookup_valid_o=imem_if.req_valid&&!held;
    assign lookup_pc_o=pc_nxt;
    assign refine_valid_o=fresh&&!imem_if.resp_error;
    assign refine_pc_o=owner_pc;
    assign saved_lookup_o=owner_lookup;
    assign imem_if.req_valid=rst_n&&(held||(can_start&&pc_nxt[1:0]==0));
    assign imem_if.req_addr=pc_nxt;
    assign imem_if.req_id='0;
    assign imem_if.req_write=0;
    assign imem_if.req_size=2;
    assign imem_if.req_wdata=0;
    assign imem_if.req_wstrb=0;
    assign imem_if.req_memtype=0;
    assign imem_if.req_priv=3;
    assign imem_if.resp_ready=rst_n&&pending&&(stale||kill_o||insn_if.ready);
    assign idle_o=!pending&&!held&&!imem_if.req_valid&&!local_fault;
    always @(posedge clk) if(rst_n) begin
        assert(!(pending&&held)) else $fatal(1,"Fetch owner overlaps held offer");
        assert(!(pending&&local_fault)) else $fatal(1,"Memory and local fault owner overlap");
        assert(!imem_if.resp_valid||(pending&&imem_if.resp_id=='0)) else $fatal(1,"Unowned instruction response");
        assert(!(accepted&&pending&&!response)) else $fatal(1,"Instruction owner reused before completion");
        assert(!(fresh&&accepted&&!f_fire)) else $fatal(1,"Successor offered before token admission");
        assert(!kill_o||!f_fire) else $fatal(1,"Killed frontend token admitted");
    end
    a_token_hold: assert property (@(posedge clk) disable iff(!rst_n)
        insn_if.valid&&!insn_if.ready |=> kill_o || (insn_if.valid&&
        $stable({insn_if.pc,insn_if.insn,insn_if.fault,insn_if.fault_misaligned,insn_if.prediction,insn_if.bp_meta})));
endmodule
