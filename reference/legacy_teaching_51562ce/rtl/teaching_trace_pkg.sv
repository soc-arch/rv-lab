// Versioned, read-only observation contract. Alternate cores drive these ports;
// no testbench code depends on implementation hierarchy. Unused fields are zero.
package teaching_trace_pkg;
    typedef struct packed {
        logic [7:0] version;
        logic [31:0] fetch_pc, fetch_insn, fetch_request_pc;
        logic fetch_valid, fetch_accepted;
        logic fetch_request_valid, fetch_request_ready, fetch_request_accepted;
        logic fetch_response_valid, fetch_response_ready, fetch_response_accepted, fetch_response_error;
        logic fetch_request_id, fetch_response_id;
        logic [31:0] execute_pc, execute_insn;
        logic execute_valid;
        logic [7:0] execute_state;
        logic stage_fetch, stage_decode, stage_execute, stage_memory, stage_writeback;
        logic unit_alu, unit_branch, unit_mul, unit_div, unit_lsu;
        logic [4:0] rs1, rs2, rd;
        logic rs1_used, rs2_used;
        logic [31:0] rs1_value, rs2_value, wb_value;
        logic wb_enable;
        logic memory_valid, memory_write, memory_response_valid;
        logic memory_request_ready, memory_request_accepted;
        logic memory_response_ready, memory_response_accepted, memory_response_error;
        logic memory_request_id, memory_response_id;
        logic [1:0] memory_size;
        logic [31:0] memory_pc, memory_addr, memory_data, memory_read_data;
        logic [3:0] memory_wstrb;
        logic commit_valid;
        logic [31:0] commit_pc, commit_insn;
        logic [4:0] commit_rd;
        logic [31:0] commit_rd_data;
        logic commit_rd_we;
        logic redirect_valid;
        logic [31:0] redirect_pc;
        logic trap_valid;
        logic [31:0] trap_cause, trap_pc, trap_value;
    } cpu_trace_t;
endpackage
