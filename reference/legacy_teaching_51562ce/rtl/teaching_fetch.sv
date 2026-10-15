// Blocking instruction-memory client: one live request and one response slot.
// Prefetch overlaps execution; redirects drain obsolete requests and responses.
module teaching_fetch #(parameter logic [31:0] RESET_PC=32'h8000_0000) (
    input logic clk, rst_n, drain_req_i,
    output logic idle_o,
    mem_if.master imem_if,
    insn_supply_if.frontend insn_if
);
    logic [31:0] next_pc, pending_pc, held_pc, buf_pc, buf_insn;
    logic pending, stale, held, held_stale, buf_valid, buf_fault, buf_misaligned;
    wire redirect = insn_if.redirect_valid || insn_if.flush;
    wire response = pending && imem_if.resp_valid && imem_if.resp_ready;
    wire fresh = response && !stale && !redirect;
    wire fresh_visible = fresh && !drain_req_i;
    assign insn_if.valid = rst_n && !redirect && !drain_req_i && (buf_valid || fresh_visible);
    assign insn_if.pc = buf_valid ? buf_pc : pending_pc;
    assign insn_if.insn = buf_valid ? buf_insn : imem_if.resp_error ? 32'h00000013 : imem_if.resp_rdata;
    assign insn_if.fault = buf_valid ? buf_fault : imem_if.resp_error;
    assign insn_if.fault_misaligned = buf_valid && buf_misaligned;
    assign insn_if.predicted_taken = 0;
    assign insn_if.predicted_target = 0;
    assign insn_if.predicted_ghr_snapshot = 0;
    wire admitted = insn_if.valid && insn_if.ready;
    wire room = !buf_valid || admitted;
    // Do not reuse the sole ID in the response cycle: clear ownership first.
    assign imem_if.req_valid = rst_n && (held ||
        (!drain_req_i && !redirect && !pending && room && next_pc[1:0]==0));
    assign imem_if.req_addr = held ? held_pc : next_pc;
    assign imem_if.req_id = '0;
    assign imem_if.req_write = 0;
    assign imem_if.req_size = 2'd2;
    assign imem_if.req_wdata = 0;
    assign imem_if.req_wstrb = 0;
    assign imem_if.req_memtype = 0; // This profile maps uncached normal SRAM only.
    assign imem_if.req_priv = 2'd3;
    assign imem_if.resp_ready = rst_n && pending;
    wire accepted = imem_if.req_valid && imem_if.req_ready;
    assign idle_o = !pending && !held && !imem_if.req_valid;
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            next_pc<=RESET_PC; pending_pc<=0; held_pc<=0; buf_pc<=0; buf_insn<=0;
            pending<=0; stale<=0; held<=0; held_stale<=0;
            buf_valid<=0; buf_fault<=0; buf_misaligned<=0;
        end else begin
            if (imem_if.req_valid && !imem_if.req_ready && !held) begin
                held<=1; held_pc<=imem_if.req_addr; held_stale<=0;
            end
            if (response) begin pending<=0; stale<=0; end
            if (admitted && buf_valid) buf_valid<=0;
            if (fresh && !admitted) begin
                buf_valid<=1; buf_pc<=pending_pc;
                buf_insn<=imem_if.resp_error ? 32'h00000013 : imem_if.resp_rdata;
                buf_fault<=imem_if.resp_error; buf_misaligned<=0;
            end
            if (accepted) begin
                held<=0; held_stale<=0; pending<=1; pending_pc<=imem_if.req_addr;
                stale<=held_stale || redirect;
                if (!held_stale && !redirect) next_pc<=imem_if.req_addr+4;
            end
            // A malformed redirect is represented as an instruction-address
            // exception token, never as an unaligned bus transaction.
            if (!pending && !held && room && !drain_req_i && !redirect && next_pc[1:0]!=0) begin
                buf_valid<=1; buf_pc<=next_pc; buf_insn<=32'h00000013;
                buf_fault<=1; buf_misaligned<=1;
            end
            if (redirect) begin
                next_pc<=insn_if.redirect_pc; buf_valid<=0;
                if (pending && !response) stale<=1;
                if (held && !accepted) held_stale<=1;
            end
        end
    end
    always @(posedge clk) if (rst_n) begin
        assert (!(pending && buf_valid)) else $fatal(1,"Fetch response storage overcommit");
        assert (!imem_if.resp_valid || (pending && imem_if.resp_id=='0))
            else $fatal(1,"Unowned instruction response");
    end
endmodule
