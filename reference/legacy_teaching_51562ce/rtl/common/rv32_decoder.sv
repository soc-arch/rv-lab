// Local editable teaching snapshot; see SOURCE_SNAPSHOT.json for provenance.
// =============================================================================
// rv32_decoder — RV32IM combinational decoder + immediate generator
//



//
// Input:  32-bit RISC-V instruction (opcode + funct3 + funct7 + reg fields + imm).
// Output: split fields + is_* class flags + 5 immediate forms (I/S/B/U/J).
//

//
// RV32IM opcode coverage:
//   LUI(0x37), AUIPC(0x17), JAL(0x6f), JALR(0x67), BRANCH(0x63),
//   LOAD(0x03), STORE(0x23), OP_IMM(0x13), OP(0x33, funct7=0x01 = MUL/DIV).
//

// =============================================================================

module rv32_decoder (
    input  logic [31:0] insn,

    // Effective-address low bits (for misalign check).  Purely combinational —
    // decoder only uses it for is_misalign_* outputs.  Cores that don't yet
    // have the computed effective address at decode time may tie 2'b00 and
    // ignore is_misalign_*; then perform the same check at EX stage when
    // alu_result[1:0] becomes available.
    input  logic [1:0]  addr_lo,


    output logic [6:0]  opcode,
    output logic [4:0]  rd,
    output logic [4:0]  rs1,
    output logic [4:0]  rs2,
    output logic [2:0]  funct3,
    output logic [6:0]  funct7,

    // Immediate forms (sign-extended to 32b where applicable)
    output logic [31:0] imm_i,   // I-type (ALU-imm, LOAD, JALR)
    output logic [31:0] imm_s,   // S-type (STORE)
    output logic [31:0] imm_b,   // B-type (BRANCH)
    output logic [31:0] imm_u,   // U-type (LUI, AUIPC)
    output logic [31:0] imm_j,   // J-type (JAL)


    output logic        is_load,
    output logic        is_store,
    output logic        is_branch,
    output logic        is_jal,
    output logic        is_jalr,
    output logic        is_alu_reg,   // OP (R-type)
    output logic        is_alu_imm,   // OP_IMM (I-type ALU)
    output logic        is_lui,
    output logic        is_auipc,
    output logic        is_muldiv,    // is_alu_reg && funct7 == 0x01
    output logic        is_mul,       // is_muldiv && funct3[2] == 0
    output logic        is_div,       // is_muldiv && funct3[2] == 1

    // System, CSR and trap-class decoding.
    output logic        is_system,    // opcode == 0x73 (SYSTEM)
    output logic        is_csr,       // SYSTEM + funct3 in {1..3, 5..7}
    output logic        is_csr_imm,   // CSR immediate variants (funct3[2]=1)
    output logic        is_mret,      // SYSTEM + funct3=0 + imm12=0x302
    output logic        is_ecall,     // SYSTEM + funct3=0 + imm12=0x000
    output logic        is_ebreak,    // SYSTEM + funct3=0 + imm12=0x001
    output logic        is_fence,     // opcode 0x0f (FENCE family; treat as NOP)
    output logic        is_fence_i,   // FENCE + funct3=0b001 (Zifencei) — needs IF flush on pipelined cores
    output logic        is_illegal,   // opcode not recognized

    output logic [11:0] csr_addr,     // insn[31:20] — CSR address for is_csr


    output logic        needs_wb,
    output logic        needs_mem,    // is_load || is_store


    //   LH/LHU/SH  : addr_lo[0] != 0      → misalign
    //   LW/SW      : addr_lo[1:0] != 2'b00 → misalign

    // RISC-V priv spec causes: 4 (load misalign), 6 (store misalign).
    output logic        is_misalign_load,
    output logic        is_misalign_store
);

    // ── Field extraction ────────────────────────────────────────────────────
    assign opcode = insn[6:0];
    assign rd     = insn[11:7];
    assign rs1    = insn[19:15];
    assign rs2    = insn[24:20];
    assign funct3 = insn[14:12];
    assign funct7 = insn[31:25];

    // ── Immediate generation (sign-extended) ───────────────────────────────
    assign imm_i = {{20{insn[31]}}, insn[31:20]};
    assign imm_s = {{20{insn[31]}}, insn[31:25], insn[11:7]};
    assign imm_b = {{19{insn[31]}}, insn[31], insn[7],
                    insn[30:25], insn[11:8], 1'b0};
    assign imm_u = {insn[31:12], 12'b0};
    assign imm_j = {{11{insn[31]}}, insn[31], insn[19:12],
                    insn[20], insn[30:21], 1'b0};

    // ── Opcode constants (RV32IM + SYSTEM/FENCE) ───────────────────────────
    localparam logic [6:0] OP_LUI    = 7'b0110111;
    localparam logic [6:0] OP_AUIPC  = 7'b0010111;
    localparam logic [6:0] OP_JAL    = 7'b1101111;
    localparam logic [6:0] OP_JALR   = 7'b1100111;
    localparam logic [6:0] OP_BRANCH = 7'b1100011;
    localparam logic [6:0] OP_LOAD   = 7'b0000011;
    localparam logic [6:0] OP_STORE  = 7'b0100011;
    localparam logic [6:0] OP_OP_IMM = 7'b0010011;
    localparam logic [6:0] OP_OP     = 7'b0110011;
    localparam logic [6:0] OP_SYSTEM = 7'b1110011;
    localparam logic [6:0] OP_FENCE  = 7'b0001111;

    // ── Class flags ─────────────────────────────────────────────────────────
    assign is_load    = (opcode == OP_LOAD);
    assign is_store   = (opcode == OP_STORE);
    assign is_branch  = (opcode == OP_BRANCH);
    assign is_jal     = (opcode == OP_JAL);
    assign is_jalr    = (opcode == OP_JALR);
    assign is_alu_reg = (opcode == OP_OP);
    assign is_alu_imm = (opcode == OP_OP_IMM);
    assign is_lui     = (opcode == OP_LUI);
    assign is_auipc   = (opcode == OP_AUIPC);
    assign is_muldiv  = is_alu_reg && (funct7 == 7'b0000001);
    assign is_mul     = is_muldiv && (funct3[2] == 1'b0);
    assign is_div     = is_muldiv && (funct3[2] == 1'b1);

    // ── SYSTEM / CSR / trap-class ───────────────────────────────────────────
    assign is_system  = (opcode == OP_SYSTEM);
    assign is_fence   = (opcode == OP_FENCE);
    // Zifencei: fence.i = FENCE opcode + funct3=0b001 (distinguish from plain fence).
    assign is_fence_i = is_fence && (funct3 == 3'b001);
    // CSR instructions: funct3 ∈ {1 (RW), 2 (RS), 3 (RC), 5 (RWI), 6 (RSI), 7 (RCI)}
    //   funct3 != 0 under OP_SYSTEM covers them all.
    assign is_csr     = is_system && (funct3 != 3'b000);
    assign is_csr_imm = is_csr && funct3[2];   // funct3 5/6/7 are immediate variants
    // PRIV group (funct3=0): MRET / ECALL / EBREAK (all rs1=0, rd=0, funct7-encoded imm12)
    assign is_mret    = is_system && (funct3 == 3'b000) && (insn[31:20] == 12'h302)
                        && (insn[19:15] == 5'd0) && (insn[11:7] == 5'd0);
    assign is_ecall   = is_system && (funct3 == 3'b000) && (insn[31:20] == 12'h000)
                        && (insn[19:15] == 5'd0) && (insn[11:7] == 5'd0);
    assign is_ebreak  = is_system && (funct3 == 3'b000) && (insn[31:20] == 12'h001)
                        && (insn[19:15] == 5'd0) && (insn[11:7] == 5'd0);

    // ── Illegal instruction detect (minimal) ────────────────────────────────
    //   Unknown opcode, OR SYSTEM w/ funct3=0 not matching MRET/ECALL/EBREAK.
    //   Finer-grained illegal cases (e.g., shamt > 31, bad funct7) deferred.
    logic opcode_known;
    assign opcode_known = is_load | is_store | is_branch | is_jal | is_jalr
                        | is_alu_reg | is_alu_imm | is_lui | is_auipc
                        | is_system | is_fence;
    logic system_priv_unknown;
    assign system_priv_unknown = is_system && (funct3 == 3'b000)
                                 && !(is_mret | is_ecall | is_ebreak);
    assign is_illegal = ~opcode_known | system_priv_unknown;

    // CSR address (insn[31:20])
    assign csr_addr   = insn[31:20];

    // ── Derived flags ───────────────────────────────────────────────────────
    //   CSR instructions write rd (even rd=x0 is encoded; write is gated
    //   architecturally to avoid side-effects on the RF via x0 hard-zero).
    assign needs_wb   = is_alu_reg | is_alu_imm | is_lui | is_auipc
                      | is_load    | is_jal    | is_jalr | is_csr;
    assign needs_mem  = is_load | is_store;

    // ── Effective-address alignment check ──────────────────────────────────
    //   funct3[1:0]: 00=byte, 01=half, 10=word (funct3[2] = unsigned flag on
    //   loads only).  Byte access is always aligned; half needs addr_lo[0]=0;
    //   word needs addr_lo[1:0]=2'b00.
    logic size_half;
    logic size_word;
    assign size_half = (funct3[1:0] == 2'b01);
    assign size_word = (funct3[1:0] == 2'b10);

    logic addr_misalign;
    assign addr_misalign = (size_half && addr_lo[0])
                         | (size_word && (addr_lo != 2'b00));

    assign is_misalign_load  = is_load  && addr_misalign;
    assign is_misalign_store = is_store && addr_misalign;

endmodule
