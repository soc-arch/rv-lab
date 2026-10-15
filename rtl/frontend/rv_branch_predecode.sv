// =============================================================================
// HY-RV | rv_branch_predecode
// Description: Instruction predecode for static branch prediction.
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

// RV32IM whitelist only. Architectural legality and register targets belong to P.
module rv_branch_predecode (
    input logic valid_i,
    input logic [31:0] pc_i, insn_i,
    output rv_bp_pkg::bp_predecode_t predecode_o
);
    import rv_bp_pkg::*;
    logic [31:0] imm;
    always_comb begin
        predecode_o='0;
        imm=0;
        if (valid_i) begin
            case (insn_i[6:0])
                7'b1100011: if (insn_i[14:12] inside {3'b000,3'b001,3'b100,3'b101,3'b110,3'b111}) begin
                    predecode_o.kind=CFI_COND;
                    imm={{19{insn_i[31]}},insn_i[31],insn_i[7],insn_i[30:25],insn_i[11:8],1'b0};
                    predecode_o.offset_negative=insn_i[31];
                    predecode_o.direct_target_valid=1;
                end
                7'b1101111: begin
                    predecode_o.kind=CFI_JAL;
                    imm={{11{insn_i[31]}},insn_i[31],insn_i[19:12],insn_i[20],insn_i[30:21],1'b0};
                    predecode_o.direct_target_valid=1;
                end
                7'b1100111: if (insn_i[14:12]==0) predecode_o.kind=CFI_JALR;
                default: begin end
            endcase
            if (predecode_o.direct_target_valid) begin
                predecode_o.direct_target=pc_i+imm;
                predecode_o.target_aligned=(predecode_o.direct_target[1:0]==0);
            end
        end
    end
endmodule
