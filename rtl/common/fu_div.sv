// =============================================================================
// HY-RV | fu_div
// Description: Multicycle RV32M division and remainder unit.
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
// fu_div — RV32 Integer Divider (HY-RV FU pool member)
//
// Structure: restoring 1-bit-per-cycle iterative divider with a 3-state FSM
// (IDLE → DIVIDE → FINISH) driving a single {remainder, dividend} shift
// register.  Structural reference: CVA6 `serdiv.sv` (Solderpad v0.51, ETH
// Zurich — Schaffner/Traber, 2018).  Clean-room reimplementation.
//
// Key difference from CVA6 serdiv: the **leading-zero-count early termination
// is disabled** in this pool member.  Reasoning (doc/wiki/architecture/
// fu_pool_mul_div.md §3.2): the current DPI lock-step timing model is static
// (opcode-based dwell prediction), so operand-dependent iteration counts
// would break the 0-cycle-error invariant agreed on 2026-04-19 for in-order
// cores.  A sibling unit `fu_div_early` with LZC + data-dependent DPI hook
// is scheduled as a post-plan round.
//
// Latency / throughput:
//   L  = 1 (load) + 32 (iterations) + 0 (result in FINISH)
//      = **33 cycles** from valid_in accept to valid_out rise (then FINISH
//        holds valid_out until ready_out = 1).
//   II = L (blocking — ready_in low throughout DIVIDE/FINISH)
//
// Interface follows the common FU protocol in doc/wiki/architecture/
// datapath_p0_p1.md §1.3.  RISC-V M-extension div-by-zero and signed
// overflow (INT_MIN / -1) are non-trapping — we produce the spec-mandated
// result and leave xcpt_out = 0.
//
// Supported ops (2-bit, from funct3[1:0]):
//   DIV_OP_DIV  = 2'd0   signed / signed,   quotient
//   DIV_OP_DIVU = 2'd1   unsigned / unsigned, quotient
//   DIV_OP_REM  = 2'd2   signed / signed,   remainder
//   DIV_OP_REMU = 2'd3   unsigned / unsigned, remainder
// =============================================================================

module fu_div #(
    parameter int XLEN  = 32,
    parameter int TAG_W = 3
) (
    input  logic                 clk,
    input  logic                 rst_n,

    // Request
    input  logic [1:0]           op,
    input  logic [XLEN-1:0]      operand_a,
    input  logic [XLEN-1:0]      operand_b,
    input  logic                 valid_in,
    output logic                 ready_in,
    input  logic [TAG_W-1:0]     tag_in,
    input  logic                 flush,        // optional pipeline flush

    // Response
    output logic [XLEN-1:0]      result,
    output logic                 valid_out,
    input  logic                 ready_out,
    output logic [TAG_W-1:0]     tag_out,
    output logic                 xcpt_out
);

    localparam logic [1:0] DIV_OP_DIV  = 2'd0;
    localparam logic [1:0] DIV_OP_DIVU = 2'd1;
    localparam logic [1:0] DIV_OP_REM  = 2'd2;
    localparam logic [1:0] DIV_OP_REMU = 2'd3;

    typedef enum logic [1:0] {
        S_IDLE   = 2'b00,
        S_DIVIDE = 2'b01,
        S_FINISH = 2'b10
    } state_t;

    state_t state_q, state_d;

    // ── Latched request context ────────────────────────────────────────
    logic              is_signed;       // 1 if DIV or REM
    logic              is_rem;          // 1 if REM/REMU
    logic              sign_a_q, sign_b_q;
    logic              op_b_zero_q;
    logic              overflow_q;      // signed INT_MIN / -1
    logic [XLEN-1:0]   op_a_orig_q;     // raw operand_a (for div-by-0 REM output)
    logic [TAG_W-1:0]  tag_q;
    logic [1:0]        op_q;

    // ── Iteration state ────────────────────────────────────────────────
    // {remainder[XLEN-1:0], dividend[XLEN-1:0]} shifted left one bit per
    // cycle.  After XLEN iterations: upper half = remainder, lower half =
    // quotient (with the just-computed bit LSB-first in lower[0]).
    logic [2*XLEN-1:0] accum_q, accum_d;
    logic [XLEN-1:0]   op_b_mag_q;
    logic [5:0]        cnt_q, cnt_d;    // fits 32 iters comfortably

    // ── Combinational operand-prep (IDLE load path) ────────────────────
    logic [XLEN-1:0] op_a_mag, op_b_mag;
    logic            signed_op;
    logic            sign_a, sign_b;
    logic            op_b_zero;
    logic            overflow;

    assign signed_op = (op == DIV_OP_DIV) | (op == DIV_OP_REM);
    assign sign_a    = signed_op & operand_a[XLEN-1];
    assign sign_b    = signed_op & operand_b[XLEN-1];
    assign op_a_mag  = sign_a ? (~operand_a + 32'd1) : operand_a;
    assign op_b_mag  = sign_b ? (~operand_b + 32'd1) : operand_b;
    assign op_b_zero = (operand_b == '0);
    assign overflow  = signed_op & (operand_a == {1'b1, {XLEN-1{1'b0}}}) &
                                   (operand_b == {XLEN{1'b1}});

    // ── Restoring step (DIVIDE path) ───────────────────────────────────
    // shifted = accum_q << 1; the upper half (candidate remainder) is
    // test-subtracted against op_b_mag_q.  If it fits, subtract + set q-bit.
    logic [2*XLEN-1:0] accum_shifted;
    logic [XLEN-1:0]   test_rem;
    logic              fits;

    assign accum_shifted = {accum_q[2*XLEN-2:0], 1'b0};
    assign test_rem      = accum_shifted[2*XLEN-1:XLEN];
    assign fits          = (test_rem >= op_b_mag_q);

    always_comb begin
        if (fits)
            accum_d = {test_rem - op_b_mag_q, accum_shifted[XLEN-1:1], 1'b1};
        else
            accum_d = accum_shifted;
    end

    // ── FSM + counter ──────────────────────────────────────────────────
    always_comb begin
        state_d   = state_q;
        cnt_d     = cnt_q;
        ready_in  = 1'b0;
        valid_out = 1'b0;
        case (state_q)
            S_IDLE: begin
                ready_in = 1'b1;
                if (valid_in) begin
                    state_d = S_DIVIDE;
                    cnt_d   = 6'd31;            // 32 iterations: 31 → 0
                end
            end
            S_DIVIDE: begin
                if (cnt_q == 6'd0) state_d = S_FINISH;
                else               cnt_d = cnt_q - 6'd1;
            end
            S_FINISH: begin
                valid_out = 1'b1;
                if (ready_out) state_d = S_IDLE;
            end
            default: state_d = S_IDLE;
        endcase

        if (flush) state_d = S_IDLE;
    end

    // ── Regs ───────────────────────────────────────────────────────────
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state_q     <= S_IDLE;
            cnt_q       <= '0;
            accum_q     <= '0;
            op_b_mag_q  <= '0;
            op_a_orig_q <= '0;
            sign_a_q    <= 1'b0;
            sign_b_q    <= 1'b0;
            op_b_zero_q <= 1'b0;
            overflow_q  <= 1'b0;
            is_signed   <= 1'b0;
            is_rem      <= 1'b0;
            tag_q       <= '0;
            op_q        <= DIV_OP_DIV;
        end else begin
            state_q <= state_d;

            if (state_q == S_IDLE && valid_in && ready_in) begin
                // Load on handshake
                accum_q     <= {32'b0, op_a_mag};
                op_b_mag_q  <= op_b_mag;
                op_a_orig_q <= operand_a;
                sign_a_q    <= sign_a;
                sign_b_q    <= sign_b;
                op_b_zero_q <= op_b_zero;
                overflow_q  <= overflow;
                is_signed   <= signed_op;
                is_rem      <= op[1];
                tag_q       <= tag_in;
                op_q        <= op;
                cnt_q       <= cnt_d;
            end else if (state_q == S_DIVIDE) begin
                accum_q <= accum_d;
                cnt_q   <= cnt_d;
            end
        end
    end

    // ── Result composition (RISC-V M-ext corner-case compliant) ────────
    logic [XLEN-1:0] quotient_raw, remainder_raw;
    logic [XLEN-1:0] quotient_signed, remainder_signed;
    logic [XLEN-1:0] quotient_out, remainder_out;

    assign quotient_raw    = accum_q[XLEN-1:0];
    assign remainder_raw   = accum_q[2*XLEN-1:XLEN];
    // Signed result recovery: quotient sign = sign_a XOR sign_b, remainder
    // sign = sign_a (dividend sign).
    assign quotient_signed  = (sign_a_q ^ sign_b_q) ? (~quotient_raw  + 32'd1) : quotient_raw;
    assign remainder_signed = sign_a_q              ? (~remainder_raw + 32'd1) : remainder_raw;

    always_comb begin
        if (op_b_zero_q) begin
            // RV32M spec: DIV/DIVU return all-1s, REM/REMU return op_a.
            quotient_out  = {XLEN{1'b1}};
            remainder_out = op_a_orig_q;
        end else if (overflow_q) begin
            // INT_MIN / -1: DIV = INT_MIN (= op_a_orig_q), REM = 0.
            quotient_out  = op_a_orig_q;
            remainder_out = '0;
        end else if (is_signed) begin
            quotient_out  = quotient_signed;
            remainder_out = remainder_signed;
        end else begin
            quotient_out  = quotient_raw;
            remainder_out = remainder_raw;
        end

        result = is_rem ? remainder_out : quotient_out;
    end

    assign tag_out  = tag_q;
    assign xcpt_out = 1'b0;

endmodule
