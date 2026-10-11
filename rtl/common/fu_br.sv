// Local editable teaching snapshot; see SOURCE_SNAPSHOT.json for provenance.
// =============================================================================
// fu_br — RV32I Branch / Jump Unit (HY-RV FU pool member)
//



//

//   BR (BEQ/BNE/BLT/BGE/BLTU/BGEU) : taken = compare(rs1, rs2, funct3),
//                                    target_pc = pc + imm_b,
//                                    result = 0 (no link)
//   JAL                             : taken = 1,
//                                    target_pc = pc + imm_j,
//                                    result = pc + 4 (link)
//   JALR                            : taken = 1,
//                                    target_pc = (rs1 + imm_i) & ~1,
//                                    result = pc + 4 (link)
//

//   4'b0xxx : BR, xxx = funct3[2:0]
//     0 BEQ · 1 BNE · 4 BLT · 5 BGE · 6 BLTU · 7 BGEU (2/3 reserved)
//   4'b1000 : JAL
//   4'b1001 : JALR
//

//   is_branch → imm_b · is_jal → imm_j · is_jalr → imm_i (I-type)
//
// Latency / throughput:
//   L  = 0 (pure combinational), II = 1
//

// =============================================================================

module fu_br #(
    parameter int XLEN  = 32,
    parameter int TAG_W = 3
) (
    input  logic                 clk,    // unused (L=0); kept for signature uniformity
    input  logic                 rst_n,  // unused

    // ── Common FU pool signature ──────────────────────────────────────
    input  logic [3:0]           op,
    input  logic [XLEN-1:0]      operand_a,   // rs1
    input  logic [XLEN-1:0]      operand_b,   // rs2 (BR only; unused for JMP)
    input  logic                 valid_in,
    output logic                 ready_in,
    input  logic [TAG_W-1:0]     tag_in,

    output logic [XLEN-1:0]      result,      // link address (PC+4) for JAL/JALR, else 0
    output logic                 valid_out,
    input  logic                 ready_out,
    output logic [TAG_W-1:0]     tag_out,
    output logic                 xcpt_out,

    // ── BRU-specific ports ────────────────────────────────────────────
    input  logic [XLEN-1:0]      pc_i,        // PC of this instruction
    input  logic [XLEN-1:0]      imm_i,       // pre-muxed imm_b / imm_j / imm_i
    output logic                 taken,       // branch taken OR JAL/JALR (always 1)
    output logic [XLEN-1:0]      target_pc    // redirect target
);

    // ── op decode ────────────────────────────────────────────────────
    localparam logic [3:0] OP_JAL  = 4'b1000;
    localparam logic [3:0] OP_JALR = 4'b1001;

    logic is_jal, is_jalr, is_branch;
    assign is_jal    = (op == OP_JAL);
    assign is_jalr   = (op == OP_JALR);
    assign is_branch = ~op[3];       // BR family: op[3]=0

    // ── Compare for BR (uses funct3 in op[2:0]) ──────────────────────
    logic compare_taken;
    always_comb begin
        unique case (op[2:0])
            3'b000: compare_taken = (operand_a == operand_b);                    // BEQ
            3'b001: compare_taken = (operand_a != operand_b);                    // BNE
            3'b100: compare_taken = ($signed(operand_a)  <  $signed(operand_b)); // BLT
            3'b101: compare_taken = ($signed(operand_a) >=  $signed(operand_b)); // BGE
            3'b110: compare_taken = (operand_a  <  operand_b);                   // BLTU
            3'b111: compare_taken = (operand_a >=  operand_b);                   // BGEU
            default: compare_taken = 1'b0;
        endcase
    end


    assign taken = is_jal | is_jalr | (is_branch & compare_taken);

    // ── Target address ───────────────────────────────────────────────
    // BR / JAL : pc_i + imm_i
    // JALR     : (operand_a + imm_i) & ~1
    logic [XLEN-1:0] target_base;
    assign target_base = is_jalr ? operand_a : pc_i;

    logic [XLEN-1:0] target_raw;
    assign target_raw = target_base + imm_i;
    assign target_pc  = is_jalr ? (target_raw & ~{{(XLEN-1){1'b0}}, 1'b1}) : target_raw;

    // ── Link address (PC+4) for JAL/JALR, zero for BR ────────────────
    assign result = (is_jal | is_jalr) ? (pc_i + 32'd4) : {XLEN{1'b0}};

    // ── Handshake ────────────────────────────────────────────────────
    assign ready_in  = 1'b1;
    assign valid_out = valid_in;
    assign tag_out   = tag_in;
    assign xcpt_out  = 1'b0;

    // verilator lint_off UNUSED
    wire _unused_ok = &{1'b0, clk, rst_n, ready_out, 1'b0};
    // verilator lint_on UNUSED

endmodule
