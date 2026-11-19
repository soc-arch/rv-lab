// =============================================================================
// HY-RV | xif_lite_if
// Description: Lab 10 blocking coprocessor interface (XIF-lite): issue and result channels.
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

// XIF-lite is a teaching interface. Its channel names follow the CORE-V
// eXtension Interface (CV-X-IF) 1.0 vocabulary, but it is NOT CV-X-IF
// compliant: one instruction at a time, no ID, no commit channel and no
// memory channel. See ext/README.md for the full contract and the mapping.
//
// Issue channel (core -> coprocessor), valid/ready:
//   The core offers one custom-1 instruction with both source register values.
//   It offers only non-speculative instructions, so no commit/kill is needed.
//   While issue_valid=1 and issue_ready=0, every issue_* payload stays stable.
//   In the handshake cycle the coprocessor answers combinationally:
//     issue_accept=1    the coprocessor owns the instruction and will complete it.
//     issue_accept=0    not a coprocessor instruction: the core raises an
//                       illegal-instruction exception. No coprocessor state changes.
//     issue_writeback   the accepted instruction will write rd; 0 when rejected.
//
// Result channel (coprocessor -> core), valid/ready:
//   Exactly one result for every accepted instruction, no earlier than the
//   cycle after the issue handshake. Outputs come from coprocessor registers
//   and stay stable until result_ready. result_we must equal issue_writeback.
//   The core retires the instruction in the result handshake cycle.
interface xif_lite_if;
    logic        issue_valid;
    logic        issue_ready;
    logic [31:0] issue_insn;
    logic [31:0] issue_pc;
    logic [31:0] issue_rs1;
    logic [31:0] issue_rs2;
    logic        issue_accept;
    logic        issue_writeback;

    logic        result_valid;
    logic        result_ready;
    logic [31:0] result_data;
    logic        result_we;

    modport core (
        output issue_valid, issue_insn, issue_pc, issue_rs1, issue_rs2, result_ready,
        input  issue_ready, issue_accept, issue_writeback, result_valid, result_data, result_we
    );
    modport coproc (
        input  issue_valid, issue_insn, issue_pc, issue_rs1, issue_rs2, result_ready,
        output issue_ready, issue_accept, issue_writeback, result_valid, result_data, result_we
    );
endinterface
