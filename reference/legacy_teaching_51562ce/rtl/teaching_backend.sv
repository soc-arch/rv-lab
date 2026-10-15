// Serialized execution backend with one instruction holding register.
// Teaching map: DECODE/RF -> EXECUTE/FUs -> MEMORY -> WRITEBACK -> CONTROL.
// These are functional responsibilities, NOT five independent pipeline stages.
// The separate frontend can hold the next fetched instruction while this backend
// executes one instruction. Arithmetic: 1 cycle; MUL: 2; DIV: 34.
// LD/ST waits for request acceptance, response acceptance, then retires.
// Misaligned accesses trap before any memory request is offered.
// FENCE is satisfied by this ordered, unbuffered SRAM profile.
// Optional CSR/trap logic remains present but the required application ISA is RV32IM.

module teaching_backend (
    input  logic        clk,
    input  logic        rst_n,


    insn_supply_if.backend  insn_if,


    mem_if.master           dmem_if,

    // Machine-mode software, timer and external interrupt inputs.
    input  logic            irq_software_i,  // MSIP
    input  logic            irq_timer_i,     // MTIP
    input  logic            irq_external_i,  // MEIP

    // Read-only 16-bit event observation bus; bit meanings are listed below.
    // Bits 11-15 report interrupt, exception, CSR and memory-wait activity.
    output logic [15:0]     events_o,
    output logic idle_o,


    output logic            commit_valid,
    output logic [31:0]     commit_pc,
    output logic [4:0]      commit_rd,
    output logic [31:0]     commit_rd_data,
    output logic            commit_rd_we,
    output teaching_trace_pkg::cpu_trace_t trace_o
);

    // =========================================================================
    // EX substate (one-hot 8-bit)
    //   IDLE       — empty or ALU-commit or MUL/DIV dispatch cycle
    //   MEM_REQ    — hold request until accepted; may take multiple cycles
    //   MEM_RESP   — wait for owned response; capture data or take fault
    //   MEM_WB     — successful LD/ST retirement; loads also write the RF
    //   MUL_WAIT   — MUL cycle 2 (fu_mul.valid_out + commit)
    //   DIV_WAIT   — DIV cycles 2..34 (counter-gated commit at counter==0)
    // =========================================================================
    // Legacy trace values 64/128 are reserved, never used by aligned v1.
    typedef enum logic [7:0] {
        EX_IDLE      = 8'b00000001,
        EX_MEM_REQ   = 8'b00000010,
        EX_MEM_RESP  = 8'b00000100,
        EX_MEM_WB    = 8'b00001000,
        EX_MUL_WAIT  = 8'b00010000,
        EX_DIV_WAIT  = 8'b00100000,
        EX_MEM_REQ2  = 8'b01000000,   // Reserved legacy trace code
        EX_MEM_RESP2 = 8'b10000000    // Reserved legacy trace code
    } ex_state_t;

    ex_state_t   ex_substate_r, ex_substate_next;
    logic [5:0]  div_counter_r, div_counter_next;   // DIV_WAIT countdown

    // =========================================================================
    // IF/EX pipe register (boundary flop)
    // =========================================================================
    logic [31:0] pc_pipe_r;
    logic [31:0] insn_pipe_r;
    logic        valid_pipe_r;
    logic fetch_fault_r, fetch_misaligned_r, mem_entry_checked_r;
    assign idle_o = !valid_pipe_r;

    // =========================================================================

    // DECODE: instruction fields, immediate generation, and operation classes.
    //   Note: class flags are gated by valid_pipe_r downstream to avoid acting
    //   on stale/invalid pipe content.
    // =========================================================================
    logic [6:0]  opcode;
    logic [4:0]  rd_addr, rs1_addr, rs2_addr;
    logic [2:0]  funct3;
    logic [6:0]  funct7;
    logic [31:0] imm_i, imm_s, imm_b, imm_u, imm_j;

    logic dec_is_load, dec_is_store, dec_is_branch, dec_is_jal, dec_is_jalr;
    logic dec_is_alu_reg, dec_is_alu_imm, dec_is_lui, dec_is_auipc;
    logic dec_is_muldiv, dec_is_mul, dec_is_div;
    // System, CSR and privileged-instruction decode outputs.
    logic dec_is_system, dec_is_csr, dec_is_csr_imm, dec_is_mret;
    logic dec_is_ecall, dec_is_ebreak, dec_is_fence, dec_is_fence_i, dec_is_illegal;
    logic [11:0] dec_csr_addr;
    logic dec_needs_wb, dec_needs_mem;
    // Misalignment outputs — alu_result[1:0] drives addr_lo (same
    // instruction is in EX, alu_result is combinationally available).
    logic dec_is_misalign_load, dec_is_misalign_store;

    // Declare addr_lo before connecting it so no implicit wire is inferred.
    logic [31:0] alu_result;

    rv32_decoder u_decoder (
        .insn              (insn_pipe_r),
        .addr_lo           (alu_result[1:0]),
        .opcode            (opcode),
        .rd                (rd_addr),
        .rs1               (rs1_addr),
        .rs2               (rs2_addr),
        .funct3            (funct3),
        .funct7             (funct7),
        .imm_i             (imm_i),
        .imm_s             (imm_s),
        .imm_b             (imm_b),
        .imm_u             (imm_u),
        .imm_j             (imm_j),
        .is_load           (dec_is_load),
        .is_store          (dec_is_store),
        .is_branch         (dec_is_branch),
        .is_jal            (dec_is_jal),
        .is_jalr           (dec_is_jalr),
        .is_alu_reg        (dec_is_alu_reg),
        .is_alu_imm        (dec_is_alu_imm),
        .is_lui            (dec_is_lui),
        .is_auipc          (dec_is_auipc),
        .is_muldiv         (dec_is_muldiv),
        .is_mul            (dec_is_mul),
        .is_div            (dec_is_div),
        .is_system         (dec_is_system),
        .is_csr            (dec_is_csr),
        .is_csr_imm        (dec_is_csr_imm),
        .is_mret           (dec_is_mret),
        .is_ecall          (dec_is_ecall),
        .is_ebreak         (dec_is_ebreak),
        .is_fence          (dec_is_fence),
        .is_fence_i        (dec_is_fence_i),
        .is_illegal        (dec_is_illegal),
        .csr_addr          (dec_csr_addr),
        .needs_wb          (dec_needs_wb),
        .needs_mem         (dec_needs_mem),
        .is_misalign_load  (dec_is_misalign_load),
        .is_misalign_store (dec_is_misalign_store)
    );

    // Valid-gated class flags: is_* must be 0 when the held instruction is invalid.
    logic is_load, is_store, is_branch, is_jal, is_jalr;
    logic is_alu_reg, is_alu_imm, is_lui, is_auipc;
    logic is_muldiv, is_mul, is_div;
    logic is_csr, is_mret, is_ecall, is_ebreak, is_illegal;
    logic is_misalign_load, is_misalign_store;

    assign is_load    = valid_pipe_r & dec_is_load;
    assign is_store   = valid_pipe_r & dec_is_store;
    assign is_branch  = valid_pipe_r & dec_is_branch;
    assign is_jal     = valid_pipe_r & dec_is_jal;
    assign is_jalr    = valid_pipe_r & dec_is_jalr;
    assign is_alu_reg = valid_pipe_r & dec_is_alu_reg;
    assign is_alu_imm = valid_pipe_r & dec_is_alu_imm;
    assign is_lui     = valid_pipe_r & dec_is_lui;
    assign is_auipc   = valid_pipe_r & dec_is_auipc;
    assign is_muldiv  = valid_pipe_r & dec_is_muldiv;
    assign is_mul     = valid_pipe_r & dec_is_mul;
    assign is_div     = valid_pipe_r & dec_is_div;
    assign is_csr     = valid_pipe_r & dec_is_csr;
    assign is_mret    = valid_pipe_r & dec_is_mret;
    assign is_ecall   = valid_pipe_r & dec_is_ecall;
    assign is_ebreak  = valid_pipe_r & dec_is_ebreak;
    // The shared decoder classifies opcodes. Validate reserved encodings here
    // as well; future custom instructions must explicitly extend this claim.
    function automatic logic encoding_legal(input logic [31:0] w);
        case (w[6:0])
            7'h03: encoding_legal = w[14:12] inside {3'd0,3'd1,3'd2,3'd4,3'd5};
            7'h23: encoding_legal = w[14:12] inside {3'd0,3'd1,3'd2};
            7'h63: encoding_legal = w[14:12] inside {3'd0,3'd1,3'd4,3'd5,3'd6,3'd7};
            7'h67: encoding_legal = w[14:12]==0;
            7'h13: encoding_legal = w[14:12]==1 ? w[31:25]==0 :
                                   w[14:12]==5 ? (w[31:25] inside {7'h00,7'h20}) : 1'b1;
            7'h33: encoding_legal = (w[31:25] inside {7'h00,7'h01}) ||
                                   (w[31:25]==7'h20 && (w[14:12] inside {3'd0,3'd5}));
            7'h37,7'h17,7'h6f: encoding_legal = 1;
            7'h0f: encoding_legal = w[14:12] inside {3'd0,3'd1};
            7'h73: encoding_legal = (w[14:12] inside {3'd1,3'd2,3'd3,3'd5,3'd6,3'd7}) ||
                                   (w inside {32'h00000073,32'h00100073,32'h30200073,32'h10500073});
            default: encoding_legal = 0;
        endcase
    endfunction
    assign is_illegal = valid_pipe_r & (dec_is_illegal || !encoding_legal(insn_pipe_r));

    assign is_misalign_load = valid_pipe_r && dec_is_misalign_load;
    assign is_misalign_store = valid_pipe_r && dec_is_misalign_store;

    logic [11:0] csr_addr;
    assign csr_addr = dec_csr_addr;

    logic needs_writeback, needs_mem;
    assign needs_writeback = valid_pipe_r & dec_needs_wb;
    assign needs_mem       = valid_pipe_r & dec_needs_mem;

    // =========================================================================




    // =========================================================================
    logic [31:0] rs1_data, rs2_data;

    // Writeback port (defined later)
    logic [31:0] wb_data;
    logic        wb_en;

    rv32_rf #(.WB_FORWARD(1'b0)) u_rf (
        .clk        (clk),
        .rst_n      (rst_n),
        .rs1_addr   (rs1_addr),
        .rs1_data   (rs1_data),
        .rs2_addr   (rs2_addr),
        .rs2_data   (rs2_data),
        .wb_en      (wb_en),
        .wb_addr    (rd_addr),
        .wb_data    (wb_data)
    );

    // REGISTER READ: 2 asynchronous source operands; write occurs at commit.
    // Operand aliases (no separate flops — pipe_reg already flops insn_pipe_r
    // and RF values are stable as long as pipe_reg holds).
    logic [31:0] op1, op2, store_data;
    assign op1        = rs1_data;
    assign op2        = rs2_data;
    assign store_data = rs2_data;

    // =========================================================================
    // EXECUTION: ALU operand / op mux (address generation uses ADD)
    //   Core R/I-type op mapping handled by rv32_alu_op_decode.  Outer mux
    //   selects ADD (AUIPC/mem) or PASS_B (LUI).
    // =========================================================================
    localparam logic [3:0] ALU_ADD    = 4'd0;
    localparam logic [3:0] ALU_PASS_B = 4'd10;

    logic [3:0] alu_op_core;
    rv32_alu_op_decode u_alu_op (
        .funct3      (funct3),
        .funct7_bit5 (funct7[5]),
        .is_alu_imm  (is_alu_imm),
        .is_alu_reg  (is_alu_reg && !is_muldiv),
        .alu_op      (alu_op_core)
    );

    logic [31:0] alu_a, alu_b;
    logic [3:0]  alu_op;

    always_comb begin
        alu_a  = op1;
        alu_b  = op2;
        alu_op = alu_op_core;

        if (is_lui) begin
            alu_op = ALU_PASS_B;
            alu_b  = imm_u;
        end else if (is_auipc) begin
            alu_a  = pc_pipe_r;
            alu_b  = imm_u;
            alu_op = ALU_ADD;
        end else if (is_alu_imm) begin
            alu_b = imm_i;
            // alu_op already set via alu_op_core
        end else if (is_alu_reg && !is_muldiv) begin
            // alu_op already set via alu_op_core
        end else if (needs_mem) begin
            alu_b  = is_store ? imm_s : imm_i;
            alu_op = ALU_ADD;
        end
    end

    // alu_result declared above — forward-ref required by u_decoder.addr_lo.
    fu_alu #(.XLEN(32), .TAG_W(3)) u_alu (
        .clk        (clk),
        .rst_n      (rst_n),
        .op         (alu_op),
        .operand_a  (alu_a),
        .operand_b  (alu_b),
        .valid_in   (1'b1),
        .ready_in   (/*unused*/),
        .tag_in     (3'b0),
        .result     (alu_result),
        .valid_out  (/*unused, L=0*/),
        .ready_out  (1'b1),
        .tag_out    (/*unused*/),
        .xcpt_out   (/*unused*/)
    );

    // =========================================================================
    // RV32M Functional Units
    //   fu_mul: L=1, II=1 (pipelined) — 1 dispatch cycle + 1 wait = 2 total
    //   fu_div: iterative, L=33
    //
    // valid_in pulses for exactly 1 cycle at the MUL/DIV dispatch cycle, which
    // is the IDLE substate cycle when slot_ex_ has is_mul / is_div set.  On
    // the next posedge substate transitions to {MUL,DIV}_WAIT and valid_in
    // deasserts combinationally.
    // =========================================================================
    logic [31:0] mul_result, div_result;
    logic        mul_valid_out, div_valid_out;
    logic        mul_valid_in,  div_valid_in;

    assign mul_valid_in = is_mul && (ex_substate_r == EX_IDLE);
    assign div_valid_in = is_div && (ex_substate_r == EX_IDLE);

    // The serialized teaching backend selects one multiplier output stage.
    fu_mul #(.XLEN(32), .TAG_W(3), .MUL_L(1)) u_mul (
        .clk        (clk),
        .rst_n      (rst_n),
        .op         (funct3[1:0]),
        .operand_a  (op1),
        .operand_b  (op2),
        .valid_in   (mul_valid_in),
        .ready_in   (/*unused*/),
        .tag_in     (3'b0),
        .result     (mul_result),
        .valid_out  (mul_valid_out),
        .ready_out  (1'b1),
        .tag_out    (/*unused*/),
        .xcpt_out   (/*unused*/)
    );

    fu_div #(.XLEN(32), .TAG_W(3)) u_div (
        .clk        (clk),
        .rst_n      (rst_n),
        .op         (funct3[1:0]),
        .operand_a  (op1),
        .operand_b  (op2),
        .valid_in   (div_valid_in),
        .ready_in   (/*unused*/),
        .tag_in     (3'b0),
        .flush      (1'b0),
        .result     (div_result),
        .valid_out  (div_valid_out),
        .ready_out  (ex_substate_r == EX_DIV_WAIT),
        .tag_out    (/*unused*/),
        .xcpt_out   (/*unused*/)
    );

    // =========================================================================
    // fu_br — combinational branch decision + target
    // =========================================================================
    logic [3:0]  br_op;
    logic [31:0] br_imm, br_link, br_target_pc;
    logic        br_taken;
    logic        br_valid_in;

    assign br_op  = is_jal  ? 4'b1000
                  : is_jalr ? 4'b1001
                  : {1'b0, funct3};
    assign br_imm = is_jal  ? imm_j
                  : is_jalr ? imm_i
                  :           imm_b;
    assign br_valid_in = is_branch | is_jal | is_jalr;

    fu_br #(.XLEN(32), .TAG_W(3)) u_br (
        .clk        (clk),
        .rst_n      (rst_n),
        .op         (br_op),
        .operand_a  (op1),
        .operand_b  (op2),
        .valid_in   (br_valid_in),
        .ready_in   (/*unused*/),
        .tag_in     (3'b0),
        .result     (br_link),
        .valid_out  (/*unused*/),
        .ready_out  (1'b1),
        .tag_out    (/*unused*/),
        .xcpt_out   (/*unused*/),
        .pc_i       (pc_pipe_r),
        .imm_i      (br_imm),
        .taken      (br_taken),
        .target_pc  (br_target_pc)
    );

    // =========================================================================
    // M-mode CSR file and precise trap controller.
    // Decode/fetch/target errors are detected at instruction entry; alignment
    // faults before a data request; bus faults when a response is consumed.
    // IRQs never cancel an offered or accepted memory operation.
    // Priority: exception > IRQ > return > branch.
    // =========================================================================
    logic        csr_access_valid;
    logic [31:0] csr_rdata;
    logic        csr_illegal;

    logic        trap_take;
    logic        trap_is_irq;
    logic [30:0] trap_cause;
    logic [31:0] trap_epc;
    logic [31:0] trap_tval;
    logic        mret_take;
    logic [31:0] trap_vector;
    logic [31:0] mret_target;
    logic        irq_pending;
    logic [3:0]  irq_cause;

    logic [15:0] events_bus;

    rv32_csr #(.N_HPM(4), .N_EVENTS(16)) u_csr (
        .clk              (clk),
        .rst_n            (rst_n),
        .csr_access_i     (csr_access_valid),
        .csr_addr_i       (csr_addr),
        .csr_funct3_i     (funct3),
        .csr_uimm_i       (rs1_addr),
        .csr_rs1_data_i   (op1),
        .csr_rdata_o      (csr_rdata),
        .csr_illegal_o    (csr_illegal),
        .trap_take_i      (trap_take),
        .trap_is_irq_i    (trap_is_irq),
        .trap_cause_i     (trap_cause),
        .trap_epc_i       (trap_epc),
        .trap_tval_i      (trap_tval),
        .mret_take_i      (mret_take),
        .trap_vector_o    (trap_vector),
        .mret_target_o    (mret_target),
        .irq_software_i   (irq_software_i),
        .irq_timer_i      (irq_timer_i),
        .irq_external_i   (irq_external_i),
        .irq_pending_o    (irq_pending),
        .irq_cause_o      (irq_cause),
        .events_i         (events_bus)
    );

    // =========================================================================
    // MEMORY ACCESS: byte-lane placement. Misaligned/split accesses are rejected.
    // =========================================================================
    logic        ls_span;
    logic [3:0]  first_be, second_be;
    logic [31:0] first_wdata, second_wdata;

    rv32_ls_split u_ls_split (
        .rs2_data     (store_data),
        .addr_lo      (alu_result[1:0]),
        .funct3       (funct3),
        .span         (ls_span),
        .first_be     (first_be),
        .second_be    (second_be),
        .first_wdata  (first_wdata),
        .second_wdata (second_wdata)
    );

    // =========================================================================
    // Load data flops + 2-word aligner (rv32_ls_align2).
    // =========================================================================
    logic [31:0] load_data_r;      // 1st access (EX_MEM_RESP)
    wire [31:0] load_data2_r = 32'd0; // No split accesses in this profile.
    logic [31:0] load_data;

    rv32_ls_align2 u_ls_align2 (
        .first_word   (load_data_r),
        .second_word  (load_data2_r),
        .addr_lo      (alu_result[1:0]),
        .funct3       (funct3),
        .aligned_data (load_data)
    );

    // =========================================================================
    // Commit decision (combinational)
    //   IDLE + valid_pipe + alu-like  → commit
    //   MEM_WB                        → commit
    //   MUL_WAIT                      → commit
    //   DIV_WAIT && counter==0        → commit
    // =========================================================================
    logic alu_like_in_idle;
    assign alu_like_in_idle = valid_pipe_r & ~(is_load | is_store | is_mul | is_div);

    // normal_commit_now: insn retires architecturally (WB may fire).
    logic normal_commit_now;
    assign normal_commit_now =
         ((ex_substate_r == EX_IDLE)     & alu_like_in_idle)
       |  (ex_substate_r == EX_MEM_WB)
       |  (ex_substate_r == EX_MUL_WAIT)
       | ((ex_substate_r == EX_DIV_WAIT) & (div_counter_r == 6'd0));

    // Release the backend slot after either successful retirement or a trap.
    // Faulting operations do not retire, even though the pipeline advances.
    logic trap_kill;  // blocks normal wb_en / commit_valid
    logic ex_commits_now;
    assign ex_commits_now = normal_commit_now | trap_kill;

    // Instruction-entry checks run in IDLE. Loads/stores dispatch directly to
    // MEM_REQ, where alignment is checked before valid is offered. MEM_REQ can
    // stall: mem_entry_checked_r prevents an IRQ from withdrawing held valid.
    // An accepted memory operation may subsequently fault in MEM_RESP.
    logic at_ex_entry;
    logic at_mem_entry;
    assign at_ex_entry  = valid_pipe_r & (ex_substate_r == EX_IDLE);
    assign at_mem_entry = valid_pipe_r & (ex_substate_r == EX_MEM_REQ);

    // CSR access fires at EX entry so csr_illegal is available for exception
    // detection.  rv32_csr's internal write path is gated by !csr_illegal so
    // illegal CSR never writes architectural state.
    assign csr_access_valid = at_ex_entry & is_csr & !fetch_fault_r;

    logic exception_fire;
    logic irq_fire;
    logic mret_fire;
    // trap_kill declared earlier (forward-decl for ex_commits_now)

    logic memory_align_fault, memory_resp_fault, instruction_target_fault;
    assign memory_align_fault = at_mem_entry && (is_misalign_load || is_misalign_store);
    assign memory_resp_fault = valid_pipe_r && (ex_substate_r == EX_MEM_RESP) &&
        dmem_if.resp_valid && dmem_if.resp_ready && dmem_if.resp_error;
    assign instruction_target_fault = at_ex_entry && br_valid_in && br_taken &&
        br_target_pc[1:0] != 0;
    assign exception_fire = (at_ex_entry &&
        (fetch_fault_r || is_ecall || is_ebreak || is_illegal || (is_csr && csr_illegal))) ||
        memory_align_fault || memory_resp_fault || instruction_target_fault;
    // An IRQ can preempt a memory operation only BEFORE valid is first offered.
    // Once valid has been stalled, the full request must remain stable until ready.
    assign irq_fire = (at_ex_entry || (at_mem_entry && !mem_entry_checked_r)) &&
        irq_pending && !exception_fire;
    assign mret_fire = at_ex_entry && is_mret && !exception_fire && !irq_fire;
    assign trap_take = exception_fire || irq_fire;
    assign trap_is_irq = irq_fire && !exception_fire;
    assign mret_take = mret_fire;
    assign trap_kill = trap_take || mret_take;
    always_comb begin
        trap_cause = 0;
        if (exception_fire) begin
            if (fetch_fault_r) trap_cause = fetch_misaligned_r ? 31'd0 : 31'd1;
            else if (instruction_target_fault) trap_cause = 31'd0;
            else if (memory_align_fault) trap_cause = is_store ? 31'd6 : 31'd4;
            else if (memory_resp_fault) trap_cause = is_store ? 31'd7 : 31'd5;
            else if (is_ecall) trap_cause = 31'd11;
            else if (is_ebreak) trap_cause = 31'd3;
            else trap_cause = 31'd2;
        end else if (irq_fire) trap_cause = {27'd0,irq_cause};
    end
    assign trap_epc = pc_pipe_r;
    assign trap_tval = !exception_fire ? 32'd0 :
        fetch_fault_r ? pc_pipe_r :
        instruction_target_fault ? br_target_pc :
        (memory_align_fault || memory_resp_fault) ? alu_result :
        (is_ecall || is_ebreak) ? 32'd0 : insn_pipe_r;

    // =========================================================================
    // WRITEBACK: one result mux and one architectural register write port
    // =========================================================================
    always_comb begin
        if      (is_csr)               wb_data = csr_rdata;
        else if (is_load)              wb_data = load_data;
        else if (is_mul)               wb_data = mul_result;
        else if (is_div)               wb_data = div_result;
        else if (is_jal | is_jalr)     wb_data = br_link;
        else                           wb_data = alu_result;
    end

    // Register writes occur only on normal retirement, never on a trap.
    assign wb_en = normal_commit_now & needs_writeback & (rd_addr != 5'd0) & !trap_kill;

    // =========================================================================
    // Redirect after a branch, trap or machine-mode return.
    //   Priority: trap > mret > branch.  pipe_flush == any redirect.
    // =========================================================================
    logic branch_redirect;
    assign branch_redirect = ex_commits_now & br_valid_in & br_taken & !trap_kill;

    logic pipe_flush;
    wire fence_i_redirect = normal_commit_now && dec_is_fence_i && !trap_kill;
    assign pipe_flush = branch_redirect | trap_take | mret_take | fence_i_redirect;

    logic [31:0] redirect_pc_sel;
    assign redirect_pc_sel = trap_take   ? trap_vector :
                             mret_take   ? mret_target :
                             fence_i_redirect ? pc_pipe_r + 32'd4 : br_target_pc;

    // Kept as alias for historical ex_substate logic below (replaced wholesale).
    logic do_redirect;
    assign do_redirect = pipe_flush;

    assign insn_if.redirect_valid = pipe_flush;
    assign insn_if.redirect_pc    = redirect_pc_sel;
    assign insn_if.flush          = pipe_flush;

    // =========================================================================
    // PIPELINE CONTROL: backend completion releases the fetched instruction.
    // Pipe advance + IF.ready
    // =========================================================================
    logic pipe_advance;
    assign pipe_advance = ex_commits_now | ~valid_pipe_r;
    assign insn_if.ready = pipe_advance;

    // =========================================================================
    // MEMORY REQUEST / COMPLETION: one live operation, ID 0, no posted stores.
    // RF operands and address remain stable while the instruction is held.
    // =========================================================================
    assign dmem_if.req_valid = rst_n && valid_pipe_r &&
        (ex_substate_r == EX_MEM_REQ) && !trap_kill;
    assign dmem_if.req_id = '0;
    assign dmem_if.req_addr = alu_result;
    assign dmem_if.req_write = is_store;
    assign dmem_if.req_size = funct3[1:0];
    assign dmem_if.req_wdata = first_wdata;
    assign dmem_if.req_wstrb = is_store ? first_be : 4'b0000;
    assign dmem_if.req_memtype = 2'd0;
    assign dmem_if.req_priv = 2'd3;
    assign dmem_if.resp_ready = rst_n && valid_pipe_r && (ex_substate_r == EX_MEM_RESP);

    // =========================================================================
    // Dispatch state for NEW insn (incoming on insn_if.insn this cycle)
    // =========================================================================
    logic [6:0] new_opcode;
    logic       new_is_mem;
    assign new_opcode = insn_if.insn[6:0];
    assign new_is_mem = (new_opcode == 7'b0000011) | (new_opcode == 7'b0100011);

    ex_state_t dispatch_state_sig;
    assign dispatch_state_sig = new_is_mem && encoding_legal(insn_if.insn) && !insn_if.fault
        ? EX_MEM_REQ : EX_IDLE;

    // =========================================================================
    // ex_substate_r + div_counter_r next-state
    // =========================================================================
    always_comb begin
        ex_substate_next = ex_substate_r;
        div_counter_next = div_counter_r;

        case (ex_substate_r)
            EX_IDLE: begin
                if (pipe_advance) begin
                    // Pipe_reg latches new insn this posedge.
                    if (do_redirect | ~insn_if.valid)
                        ex_substate_next = EX_IDLE;
                    else
                        ex_substate_next = dispatch_state_sig;
                end else if (valid_pipe_r) begin
                    // MUL/DIV dispatch cycle → transition to WAIT next posedge.
                    if (is_mul) begin
                        ex_substate_next = EX_MUL_WAIT;
                    end else if (is_div) begin
                        ex_substate_next = EX_DIV_WAIT;
                        div_counter_next = 6'd32;   // L_div - 1
                    end
                end
            end
            EX_MEM_REQ: begin
                if (trap_kill) ex_substate_next = EX_IDLE;
                else if (dmem_if.req_valid && dmem_if.req_ready) ex_substate_next = EX_MEM_RESP;
            end
            EX_MEM_RESP: begin
                if (trap_kill) ex_substate_next = EX_IDLE;
                else if (dmem_if.resp_valid && dmem_if.resp_ready) ex_substate_next = EX_MEM_WB;
            end
            // Reserved legacy trace states: the aligned v1 profile never enters them.
            EX_MEM_REQ2, EX_MEM_RESP2: ex_substate_next = EX_IDLE;
            EX_MEM_WB: begin
                // Successful memory completion retires and releases the slot.
                if (do_redirect | ~insn_if.valid)
                    ex_substate_next = EX_IDLE;
                else
                    ex_substate_next = dispatch_state_sig;
            end
            EX_MUL_WAIT: begin
                if (do_redirect | ~insn_if.valid)
                    ex_substate_next = EX_IDLE;
                else
                    ex_substate_next = dispatch_state_sig;
            end
            EX_DIV_WAIT: begin
                if (div_counter_r == 6'd0) begin
                    if (do_redirect | ~insn_if.valid)
                        ex_substate_next = EX_IDLE;
                    else
                        ex_substate_next = dispatch_state_sig;
                end else begin
                    div_counter_next = div_counter_r - 6'd1;
                end
            end
            default: ex_substate_next = EX_IDLE;
        endcase
    end

    // =========================================================================
    // Sequential: substate + pipe_reg + load_data_r
    //   RF write owned by u_rf instance (via wb_en/rd_addr/wb_data).
    // =========================================================================
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            ex_substate_r <= EX_IDLE;
            div_counter_r <= 6'd0;
            pc_pipe_r     <= 32'h0;
            insn_pipe_r   <= 32'h0;
            valid_pipe_r  <= 1'b0;
            fetch_fault_r <= 0; fetch_misaligned_r <= 0; mem_entry_checked_r <= 0;
            load_data_r   <= 32'h0;
        end else begin
            ex_substate_r <= ex_substate_next;
            div_counter_r <= div_counter_next;

            if (pipe_advance) mem_entry_checked_r <= 0;
            else if (at_mem_entry) mem_entry_checked_r <= 1;
            // Pipe_reg update (only on pipe_advance)
            if (pipe_advance) begin
                if (do_redirect) begin
                    valid_pipe_r <= 1'b0;   // Flush instruction slot; fetch recovery latency is variable.
                end else if (insn_if.valid) begin
                    valid_pipe_r <= 1'b1;
                    pc_pipe_r    <= insn_if.pc;
                    insn_pipe_r  <= insn_if.insn;
                    fetch_fault_r <= insn_if.fault;
                    fetch_misaligned_r <= insn_if.fault_misaligned;
                end else begin
                    valid_pipe_r <= 1'b0;
                end
            end

            // Capture only a successful, owned response.
            if (ex_substate_r == EX_MEM_RESP && dmem_if.resp_valid &&
                dmem_if.resp_ready && !dmem_if.resp_error) begin
                load_data_r <= dmem_if.resp_rdata;
            end
        end
    end

    // =========================================================================
    // Commit trace — NORMAL retire only (trap_kill does not count as commit).
    // =========================================================================
    assign commit_valid   = normal_commit_now & ~trap_kill;
    assign commit_pc      = pc_pipe_r;
    assign commit_rd      = rd_addr;
    assign commit_rd_data = wb_data;
    assign commit_rd_we   = wb_en;

    // =========================================================================
    // Read-only event bus for observing machine-mode execution.
    // The following definitions describe all 16 bits.
    //   [0] CYCLE, [1] INSTRET, [2] BRANCH_TAKEN, [3] LOAD, [4] STORE,
    //   [5] MUL, [6] DIV
    //   [7] STALL_LOADUSE — serialized backend → 0
    //   [8] STALL_MUL (EX_MUL_WAIT)  [9] STALL_DIV (EX_DIV_WAIT)
    //   [10] BRANCH_FLUSH — serialized backend → 0
    //   [11] IRQ_TAKEN  — irq_fire pulse
    //   [12] EXC_TAKEN  — exception_fire pulse
    //   [13] CSR_READ   — csr_access_valid
    //   [14] CSR_WRITE  — legal CSR write fires this cycle
    //   [15] MEM_WAIT   — in MEM_REQ or MEM_RESP (core waiting on memory slave)
    // =========================================================================
    logic csr_write_fire_ev;
    always_comb begin
        csr_write_fire_ev = 1'b0;
        if (csr_access_valid && !csr_illegal && !trap_take) begin
            unique case (funct3)
                3'b001, 3'b101: csr_write_fire_ev = 1'b1;                  // CSRRW/RWI
                3'b010, 3'b110: csr_write_fire_ev = (rs1_addr != 5'd0);    // CSRRS/RSI
                3'b011, 3'b111: csr_write_fire_ev = (rs1_addr != 5'd0);    // CSRRC/RCI
                default:        csr_write_fire_ev = 1'b0;
            endcase
        end
    end

    always_comb begin
        events_bus       = 16'd0;
        events_bus[0]    = 1'b1;
        events_bus[1]    = normal_commit_now & ~trap_kill;
        events_bus[2]    = (normal_commit_now & ~trap_kill) && br_taken &&
                           (is_branch | is_jal | is_jalr);
        events_bus[3]    = (normal_commit_now & ~trap_kill) && is_load;
        events_bus[4]    = (normal_commit_now & ~trap_kill) && is_store;
        events_bus[5]    = (normal_commit_now & ~trap_kill) && is_mul;
        events_bus[6]    = (normal_commit_now & ~trap_kill) && is_div;
        // bit 7: STALL_LOADUSE — serialized backend, always 0.
        events_bus[8]    = (ex_substate_r == EX_MUL_WAIT);
        events_bus[9]    = (ex_substate_r == EX_DIV_WAIT);
        // bit 10: BRANCH_FLUSH — serialized backend, always 0.
        events_bus[11]   = irq_fire;
        events_bus[12]   = exception_fire;
        events_bus[13]   = csr_access_valid && !csr_illegal && !trap_take;
        events_bus[14]   = csr_write_fire_ev;
        events_bus[15]   = (ex_substate_r == EX_MEM_REQ)  |
                           (ex_substate_r == EX_MEM_RESP) |
                           (ex_substate_r == EX_MEM_REQ2) |
                           (ex_substate_r == EX_MEM_RESP2);
    end

    assign events_o = events_bus;

    // =========================================================================
    // Assertions
    // =========================================================================
    // synthesis translate_off
    always @(posedge clk) begin
        if (rst_n) begin
            assert ($onehot(ex_substate_r))
                else $fatal(1,"Backend state is not one-hot: %b",ex_substate_r);
            assert (!(ex_substate_r inside {EX_MEM_REQ2,EX_MEM_RESP2}));
        end
    end
    // synthesis translate_on

    // Version 2 logical observations, sampled BEFORE the rising edge.
    // Activity markers denote useful processing, never physical switching power.
    always_comb begin
        trace_o = '0;
        trace_o.version = 8'd2;
        trace_o.execute_pc = pc_pipe_r;
        trace_o.execute_insn = insn_pipe_r;
        trace_o.execute_valid = valid_pipe_r;
        trace_o.execute_state = ex_substate_r;
        trace_o.stage_decode = valid_pipe_r &&
            ((ex_substate_r == EX_IDLE) || (ex_substate_r == EX_MEM_REQ));
        trace_o.stage_execute = valid_pipe_r && !trap_kill &&
            ((ex_substate_r == EX_IDLE) || (ex_substate_r == EX_MUL_WAIT) ||
             (ex_substate_r == EX_DIV_WAIT) || (ex_substate_r == EX_MEM_REQ));
        trace_o.stage_memory = valid_pipe_r &&
            ((ex_substate_r == EX_MEM_REQ) || (ex_substate_r == EX_MEM_RESP) ||
             (ex_substate_r == EX_MEM_REQ2) || (ex_substate_r == EX_MEM_RESP2));
        trace_o.stage_writeback = wb_en;
        trace_o.unit_alu = valid_pipe_r && !trap_kill &&
            (((ex_substate_r == EX_IDLE) &&
              (is_lui || is_auipc || is_alu_imm || (is_alu_reg && !is_muldiv))) ||
             (ex_substate_r == EX_MEM_REQ));
        trace_o.unit_branch = valid_pipe_r && br_valid_in && !trap_kill;
        trace_o.unit_mul = valid_pipe_r && is_mul && !trap_kill;
        trace_o.unit_div = valid_pipe_r && is_div && !trap_kill;
        trace_o.unit_lsu = trace_o.stage_memory;
        trace_o.rs1 = rs1_addr;
        trace_o.rs2 = rs2_addr;
        trace_o.rs1_used = is_load || is_store || is_branch || is_jalr ||
                          is_alu_imm || is_alu_reg || (is_csr && !dec_is_csr_imm);
        trace_o.rs2_used = is_store || is_branch || is_alu_reg;
        trace_o.rs1_value = rs1_data;
        trace_o.rs2_value = rs2_data;
        trace_o.rd = rd_addr;
        trace_o.wb_value = wb_data;
        trace_o.wb_enable = wb_en;
        trace_o.memory_pc = pc_pipe_r; // Owner of the request, independent of fetch.
        trace_o.commit_valid = commit_valid;
        trace_o.commit_pc = commit_pc;
        trace_o.commit_insn = insn_pipe_r;
        trace_o.commit_rd = commit_rd;
        trace_o.commit_rd_data = commit_rd_data;
        trace_o.commit_rd_we = commit_rd_we;
        trace_o.redirect_valid = insn_if.redirect_valid;
        trace_o.redirect_pc = insn_if.redirect_pc;
        trace_o.trap_valid = trap_take;
        trace_o.trap_cause = {trap_is_irq, trap_cause};
        trace_o.trap_pc = trap_epc;
        trace_o.trap_value = trap_tval;
    end

    // Architectural checks are independent of microarchitectural cycle counts.
    always @(posedge clk) if (rst_n) begin
        assert (!wb_en || (rd_addr != 0 && commit_valid));
        assert ((rs1_addr != 0 || rs1_data == 0) &&
                (rs2_addr != 0 || rs2_data == 0));
        assert (!trap_take || (!commit_valid && !wb_en && !dmem_if.req_valid));
    end

endmodule
