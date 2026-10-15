// =============================================================================
// HY-RV | insn_supply_if
// Description: Instruction token and backend control interface definitions.
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

// Local editable teaching snapshot; see SOURCE_SNAPSHOT.json for provenance.
// =============================================================================

//



//




// =============================================================================

interface insn_supply_if;

    // Token-only ports for F/link boundaries. Reverse control below remains a
    // backend compatibility contract; top explicitly fans it out to F and link.

    // ── Frontend → Backend (instruction supply) ──
    logic           valid;
    logic           ready;
    logic [31:0]    pc;
    logic [31:0]    insn;
    logic fault, fault_misaligned; // Fetch error travels with this PC/instruction slot.
    logic           predicted_taken;
    logic [31:0]    predicted_target;
    // Phase 2b — gshare BHSR snapshot at predict time.  Carried through
    // IFID/IDEX so EX resolve uses the same BHSR that produced the prediction.

    logic [7:0]     predicted_ghr_snapshot;

    // Canonical BP token record. F freezes the lookup owner metadata and
    // resolves the effective successor before first valid. The legacy fields
    // above remain compatibility observations; consumers use this record.
    rv_bp_pkg::bp_prediction_t prediction;
    rv_bp_pkg::bp_lookup_t bp_meta;

    // ── Backend → Frontend (redirect / flush) ──
    logic           redirect_valid;
    logic [31:0]    redirect_pc;        // Redirect target PC
    logic           flush;


    modport frontend (
        output valid, pc, insn, fault, fault_misaligned, predicted_taken, predicted_target, predicted_ghr_snapshot, prediction, bp_meta,
        input  ready, redirect_valid, redirect_pc, flush
    );

    modport token_source (
        output valid, pc, insn, fault, fault_misaligned, predicted_taken, predicted_target, predicted_ghr_snapshot, prediction, bp_meta,
        input ready
    );

    modport token_sink (
        input valid, pc, insn, fault, fault_misaligned, predicted_taken, predicted_target, predicted_ghr_snapshot, prediction, bp_meta,
        output ready
    );


    modport backend (
        input  valid, pc, insn, fault, fault_misaligned, predicted_taken, predicted_target, predicted_ghr_snapshot, prediction, bp_meta,
        output ready, redirect_valid, redirect_pc, flush
    );

endinterface
