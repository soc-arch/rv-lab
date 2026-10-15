// =============================================================================
// HY-RV | rv_core_simple
// Description: RV32IM P1 core integrating frontend, Q0 link, backend, and static predictor.
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

// RV32IM simple core with independent frontend, token link and backend.
// One live transaction per I/D port. No fixed SRAM response assumption remains.
module rv_core_simple #(
    parameter logic [31:0] RESET_PC=32'h8000_0000,
    parameter int unsigned INSN_QUEUE_DEPTH=0,
    parameter int unsigned BP_PROFILE=0, COND_POLICY=0,
    parameter bit EARLY_JAL_EN=0, STATIC_POLICY_EN=1, SUCCESSOR_CHECK_EN=1
) (
    input logic clk, rst_n,
    mem_if.master imem_if, dmem_if,
    input logic drain_req_i,
    output logic drain_done_o,
    input logic irq_software_i, irq_timer_i, irq_external_i,
    output logic commit_valid,
    output logic [31:0] commit_pc,
    output logic [4:0] commit_rd,
    output logic [31:0] commit_rd_data,
    output logic commit_rd_we,
    output logic [15:0] events_o,
    output rv_trace_pkg::cpu_trace_t trace_o
);
    initial begin
        if ((COND_POLICY!=0 || EARLY_JAL_EN) && !SUCCESSOR_CHECK_EN)
            $fatal(1,"Static taken prediction requires P successor checking");
        assert ($bits(imem_if.req_addr)==32 && $bits(dmem_if.req_addr)==32);
        assert ($bits(imem_if.resp_rdata)==32 && $bits(dmem_if.resp_rdata)==32);
    end
    insn_supply_if f_if();
    insn_supply_if p_if();
    wire redirect = p_if.redirect_valid || p_if.flush;
    rv_trace_pkg::cpu_trace_t backend_trace;
    logic fetch_idle, backend_idle, fetch_stopped, frontend_kill;
    logic [31:0] resume_pc,lookup_pc,refine_pc;
    logic lookup_valid,refine_valid,bp_update_valid,bp_invalidate;
    logic [2:0] redirect_reason;
    rv_bp_pkg::bp_lookup_t lookup_record,saved_lookup;
    rv_bp_pkg::bp_prediction_t effective;
    rv_bp_pkg::bp_predecode_t predecode;
    rv_bp_pkg::bp_update_t bp_update;
    rv_branch_predictor #(.BP_PROFILE(BP_PROFILE),.COND_POLICY(COND_POLICY),.EARLY_JAL_EN(EARLY_JAL_EN),.STATIC_POLICY_EN(STATIC_POLICY_EN)) u_bp (
        .clk,.rst_n,.lookup_valid_i(lookup_valid),.lookup_pc_i(lookup_pc),.lookup_record_o(lookup_record),
        .refine_valid_i(refine_valid),.refine_pc_i(refine_pc),.predecode_i(predecode),.saved_lookup_i(saved_lookup),.effective_o(effective),
        .update_valid_i(bp_update_valid),.update_i(bp_update),.invalidate_frontend_state_i(bp_invalidate)
    );
    rv_frontend #(.RESET_PC(RESET_PC)) u_frontend (
        .clk,.rst_n,.drain_req_i,.idle_o(fetch_idle),.stopped_o(fetch_stopped),.kill_o(frontend_kill),.imem_if,
        .redirect_i(redirect),.redirect_pc_i(p_if.redirect_pc),.insn_if(f_if),
        .resume_pc_i(resume_pc),.backend_idle_i(backend_idle),
        .lookup_valid_o(lookup_valid),.lookup_pc_o(lookup_pc),.lookup_record_i(lookup_record),
        .refine_valid_o(refine_valid),.refine_pc_o(refine_pc),.predecode_o(predecode),.saved_lookup_o(saved_lookup),.effective_i(effective)
    );
    rv_insn_link #(.INSN_QUEUE_DEPTH(INSN_QUEUE_DEPTH)) u_insn_link (
        .rst_n,.flush_i(frontend_kill),.f_if,.p_if
    );
    rv_backend #(.RESET_PC(RESET_PC),.SUCCESSOR_CHECK_EN(SUCCESSOR_CHECK_EN)) u_backend (
        .clk,.rst_n,.insn_if(p_if),.dmem_if,.idle_o(backend_idle),
        .irq_software_i,.irq_timer_i,.irq_external_i,
        .commit_valid,.commit_pc,.commit_rd,.commit_rd_data,.commit_rd_we,
        .events_o,.trace_o(backend_trace),
        .bp_update_valid_o(bp_update_valid),.bp_update_o(bp_update),.bp_invalidate_o(bp_invalidate),.resume_pc_o(resume_pc),.redirect_reason_o(redirect_reason)
    );
    // This unbuffered profile has no hidden posted writes or dirty cache lines.
    // Drain discards younger tokens; restart uses the architectural resume PC.
    assign drain_done_o = rst_n && drain_req_i && fetch_stopped && fetch_idle && backend_idle;
    always_comb begin
        trace_o = backend_trace;
        trace_o.fetch_pc = p_if.pc;
        trace_o.fetch_insn = p_if.insn;
        trace_o.fetch_request_pc = imem_if.req_addr;
        trace_o.fetch_valid = p_if.valid;
        trace_o.fetch_accepted = p_if.valid && p_if.ready && !p_if.redirect_valid;
        trace_o.stage_fetch = p_if.valid || imem_if.req_valid || imem_if.resp_valid;
        trace_o.fetch_request_valid = imem_if.req_valid;
        trace_o.fetch_request_ready = imem_if.req_ready;
        trace_o.fetch_request_accepted = imem_if.req_valid && imem_if.req_ready;
        trace_o.fetch_response_valid = imem_if.resp_valid;
        trace_o.fetch_response_ready = imem_if.resp_ready;
        trace_o.fetch_response_accepted = imem_if.resp_valid && imem_if.resp_ready;
        trace_o.fetch_response_error = imem_if.resp_error;
        trace_o.fetch_request_id = imem_if.req_id[0];
        trace_o.fetch_response_id = imem_if.resp_id[0];
        trace_o.memory_valid = dmem_if.req_valid;
        trace_o.memory_write = dmem_if.req_write;
        trace_o.memory_addr = dmem_if.req_addr;
        trace_o.memory_data = dmem_if.req_wdata;
        trace_o.memory_wstrb = dmem_if.req_wstrb;
        trace_o.memory_size = dmem_if.req_size;
        trace_o.memory_read_data = dmem_if.resp_rdata;
        trace_o.memory_request_ready = dmem_if.req_ready;
        trace_o.memory_request_accepted = dmem_if.req_valid && dmem_if.req_ready;
        trace_o.memory_response_valid = dmem_if.resp_valid;
        trace_o.memory_response_ready = dmem_if.resp_ready;
        trace_o.memory_response_accepted = dmem_if.resp_valid && dmem_if.resp_ready;
        trace_o.memory_response_error = dmem_if.resp_error;
        trace_o.memory_request_id = dmem_if.req_id[0];
        trace_o.memory_response_id = dmem_if.resp_id[0];
    end
    // The top-level checks use only the public channel, not testbench hierarchy.
    logic i_live, d_live;
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin i_live<=0; d_live<=0; end
        else begin
            if (imem_if.resp_valid && imem_if.resp_ready) i_live<=0;
            if (dmem_if.resp_valid && dmem_if.resp_ready) d_live<=0;
            if (imem_if.req_valid && imem_if.req_ready) i_live<=1;
            if (dmem_if.req_valid && dmem_if.req_ready) d_live<=1;
            assert (!imem_if.resp_valid || (i_live && imem_if.resp_id=='0))
                else $fatal(1,"Instruction response has no live owner");
            assert (!dmem_if.resp_valid || (d_live && dmem_if.resp_id=='0))
                else $fatal(1,"Data response has no live owner");
            assert (!(imem_if.req_valid && imem_if.req_ready && i_live &&
                !(imem_if.resp_valid && imem_if.resp_ready)));
            assert (!(dmem_if.req_valid && dmem_if.req_ready && d_live &&
                !(dmem_if.resp_valid && dmem_if.resp_ready)));
            if (dmem_if.req_valid) begin
                assert (dmem_if.req_id=='0 && dmem_if.req_size<=2);
                assert ((dmem_if.req_addr & ((32'd1 << dmem_if.req_size)-1))==0);
                assert (dmem_if.req_write ?
                    dmem_if.req_wstrb == (4'((32'd1 << (32'd1 << dmem_if.req_size))-1) << dmem_if.req_addr[1:0]) :
                    dmem_if.req_wstrb==0);
            end
            if (imem_if.req_valid) begin
                assert (imem_if.req_id=='0 && !imem_if.req_write && imem_if.req_addr[1:0]==0);
                assert (imem_if.req_size==2 && imem_if.req_wstrb==0);
            end
            assert (!drain_done_o || (!i_live && !d_live && !imem_if.req_valid && !dmem_if.req_valid));
            assert (!backend_trace.trap_valid || !commit_valid);
        end
    end
    a_i_request_hold: assert property (@(posedge clk) disable iff (!rst_n)
        imem_if.req_valid && !imem_if.req_ready |=> imem_if.req_valid &&
        $stable({imem_if.req_id,imem_if.req_addr,imem_if.req_write,imem_if.req_size,
            imem_if.req_wdata,imem_if.req_wstrb,imem_if.req_memtype,imem_if.req_priv}));
    a_d_request_hold: assert property (@(posedge clk) disable iff (!rst_n)
        dmem_if.req_valid && !dmem_if.req_ready |=> dmem_if.req_valid &&
        $stable({dmem_if.req_id,dmem_if.req_addr,dmem_if.req_write,dmem_if.req_size,
            dmem_if.req_wdata,dmem_if.req_wstrb,dmem_if.req_memtype,dmem_if.req_priv}));
    a_i_response_hold: assert property (@(posedge clk) disable iff (!rst_n)
        imem_if.resp_valid && !imem_if.resp_ready |=> imem_if.resp_valid &&
        $stable({imem_if.resp_id,imem_if.resp_rdata,imem_if.resp_error}));
    a_d_response_hold: assert property (@(posedge clk) disable iff (!rst_n)
        dmem_if.resp_valid && !dmem_if.resp_ready |=> dmem_if.resp_valid &&
        $stable({dmem_if.resp_id,dmem_if.resp_rdata,dmem_if.resp_error}));
endmodule
