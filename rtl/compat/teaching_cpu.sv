// =============================================================================
// HY-RV | teaching_cpu
// Description: Replaceable teaching CPU wrapper with memory-v1 transaction ports.
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

// Replaceable RV32 teaching CPU with HY-RV memory v1 transaction ports.
// One live transaction per I/D port. No fixed SRAM response assumption remains.
module teaching_cpu #(
    parameter logic [31:0] RESET_PC=32'h8000_0000,
    parameter int unsigned INSN_QUEUE_DEPTH=0, BP_PROFILE=0, COND_POLICY=0,
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
    output teaching_trace_pkg::cpu_trace_t trace_o
);
    rv_core_simple #(.RESET_PC(RESET_PC), .INSN_QUEUE_DEPTH(INSN_QUEUE_DEPTH),.BP_PROFILE(BP_PROFILE),.COND_POLICY(COND_POLICY),
        .EARLY_JAL_EN(EARLY_JAL_EN),.STATIC_POLICY_EN(STATIC_POLICY_EN),.SUCCESSOR_CHECK_EN(SUCCESSOR_CHECK_EN)) u_core (
        .clk,.rst_n,.imem_if,.dmem_if,.drain_req_i,.drain_done_o,
        .irq_software_i,.irq_timer_i,.irq_external_i,
        .commit_valid,.commit_pc,.commit_rd,.commit_rd_data,.commit_rd_we,
        .events_o,.trace_o
    );
endmodule
