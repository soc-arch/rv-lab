// Local editable teaching snapshot; see SOURCE_SNAPSHOT.json for provenance.
// =============================================================================

//



//




// =============================================================================

interface insn_supply_if;

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

    // ── Backend → Frontend (redirect / flush) ──
    logic           redirect_valid;
    logic [31:0]    redirect_pc;        // Redirect target PC
    logic           flush;


    modport frontend (
        output valid, pc, insn, fault, fault_misaligned, predicted_taken, predicted_target, predicted_ghr_snapshot,
        input  ready, redirect_valid, redirect_pc, flush
    );


    modport backend (
        input  valid, pc, insn, fault, fault_misaligned, predicted_taken, predicted_target, predicted_ghr_snapshot,
        output ready, redirect_valid, redirect_pc, flush
    );

endinterface
