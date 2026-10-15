// =============================================================================
// HY-RV | rv_bp_pkg
// Description: Canonical branch predecode, prediction, lookup, and update records.
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

package rv_bp_pkg;
    typedef enum logic [1:0] {CFI_NONE=0, CFI_COND=1, CFI_JAL=2, CFI_JALR=3} bp_kind_t;
    typedef enum logic [3:0] {BP_SEQ=0, BP_BTFNT=1, BP_EARLY_JAL=2} bp_source_t;
    typedef struct packed {
        logic btb_hit;
        bp_kind_t btb_kind;
        logic direction_valid, raw_taken, target_valid;
        logic [31:0] target;
        logic pht_index_valid;
        logic [7:0] pht_index;
        logic local_history_hit;
    } bp_lookup_t;
    typedef struct packed {
        logic taken;
        logic [31:0] next_pc;
        logic [3:0] source, refine_flags;
    } bp_prediction_t;
    typedef struct packed {
        bp_kind_t kind;
        logic offset_negative, direct_target_valid;
        logic [31:0] direct_target;
        logic target_aligned;
    } bp_predecode_t;
    typedef struct packed {
        logic [31:0] pc;
        bp_kind_t actual_kind;
        logic actual_taken, resolved_target_valid;
        logic [31:0] resolved_target, actual_next_pc;
        bp_prediction_t prediction;
        bp_lookup_t bp_meta;
    } bp_update_t;
endpackage
