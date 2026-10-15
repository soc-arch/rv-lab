// Local editable teaching snapshot; see SOURCE_SNAPSHOT.json for provenance.
// =============================================================================
// fu_mul — RV32 Integer Multiplier (HY-RV FU pool member)
//
// Structure: single full-width (2×XLEN) combinational multiply feeding an
// output-side shift-register chain of length MUL_L.  Mirrors CVA6
// `multiplier.sv` (Solderpad v0.51, ETH Zurich — Zaruba, 2018) at the
// structural level: the synthesizer picks the Booth/Wallace implementation
// from the $signed*$signed operator, and we supply the sign-extension +
// output-bank-select around it.  This is a clean-room reimplementation, not
// a source copy.
//
// Latency / throughput:
//   L  = MUL_L    (valid_in at cycle N → valid_out at cycle N+MUL_L)
//   II = 1        (fully pipelined — a new op may enter every cycle)
//
// MUL_L controls the number of output register stages.  The teaching backend
// selects one stage; increasing this parameter delays result, operation and
// tag together without changing the arithmetic.
//
// The request carries operation, operands and a tag.  The response returns
// result, validity, tag and exception status.  ready_in is unconditionally 1;
// the caller must be ready to consume the result when it becomes valid.
//
// Supported ops (2-bit):
//   MUL_OP_MUL    = 2'd0   lower XLEN bits of unsigned*unsigned (== signed*signed low)
//   MUL_OP_MULH   = 2'd1   upper XLEN bits of signed*signed
//   MUL_OP_MULHSU = 2'd2   upper XLEN bits of signed*unsigned
//   MUL_OP_MULHU  = 2'd3   upper XLEN bits of unsigned*unsigned
// =============================================================================

module fu_mul #(
    parameter int XLEN  = 32,
    parameter int TAG_W = 3,
    parameter int MUL_L = 1        // One output register stage by default.
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

    // Response
    output logic [XLEN-1:0]      result,
    output logic                 valid_out,
    input  logic                 ready_out,
    output logic [TAG_W-1:0]     tag_out,
    output logic                 xcpt_out
);

    localparam logic [1:0] MUL_OP_MUL    = 2'd0;
    localparam logic [1:0] MUL_OP_MULH   = 2'd1;
    localparam logic [1:0] MUL_OP_MULHSU = 2'd2;
    localparam logic [1:0] MUL_OP_MULHU  = 2'd3;

    // ── Sign-select for the two operands ────────────────────────────────
    logic sign_a, sign_b;
    always_comb begin
        unique case (op)
            MUL_OP_MULH:   begin sign_a = 1'b1; sign_b = 1'b1; end
            MUL_OP_MULHSU: begin sign_a = 1'b1; sign_b = 1'b0; end
            default:       begin sign_a = 1'b0; sign_b = 1'b0; end
        endcase
    end

    // ── Full-width multiply, combinational ──────────────────────────────
    // Extra sign bit on top of each operand forces $signed() to interpret
    // the operand correctly when we want unsigned semantics (sign_* = 0
    // zero-extends the top) or signed (sign_* = 1 replicates operand's MSB).
    logic signed [XLEN:0]     a_ext, b_ext;
    logic signed [2*XLEN+1:0] prod_full;
    logic [2*XLEN-1:0]        prod_d;

    assign a_ext = {operand_a[XLEN-1] & sign_a, operand_a};
    assign b_ext = {operand_b[XLEN-1] & sign_b, operand_b};
    assign prod_full = a_ext * b_ext;
    assign prod_d    = prod_full[2*XLEN-1:0];

    // ── Output shift-register chain (L=MUL_L, II=1) ─────────────────────
    // The chain delays the product and its validity, operation and tag together.
    // With MUL_L = 1 only prod_shift[0] is used; larger values add stages.
    logic [2*XLEN-1:0] prod_shift  [MUL_L];
    logic              valid_shift [MUL_L];
    logic [1:0]        op_shift    [MUL_L];
    logic [TAG_W-1:0]  tag_shift   [MUL_L];

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (int i = 0; i < MUL_L; i++) begin
                prod_shift[i]  <= '0;
                valid_shift[i] <= 1'b0;
                op_shift[i]    <= MUL_OP_MUL;
                tag_shift[i]   <= '0;
            end
        end else begin
            // First stage absorbs the combinational Wallace result.
            prod_shift[0]  <= prod_d;
            valid_shift[0] <= valid_in;
            op_shift[0]    <= op;
            tag_shift[0]   <= tag_in;
            // Remaining stages shift the product and associated metadata.
            for (int i = 1; i < MUL_L; i++) begin
                prod_shift[i]  <= prod_shift[i-1];
                valid_shift[i] <= valid_shift[i-1];
                op_shift[i]    <= op_shift[i-1];
                tag_shift[i]   <= tag_shift[i-1];
            end
        end
    end

    // ── Result bank select ──────────────────────────────────────────────
    always_comb begin
        unique case (op_shift[MUL_L-1])
            MUL_OP_MULH, MUL_OP_MULHSU, MUL_OP_MULHU:
                result = prod_shift[MUL_L-1][2*XLEN-1:XLEN];
            default: // MUL
                result = prod_shift[MUL_L-1][XLEN-1:0];
        endcase
    end

    // ── Handshake / status ──────────────────────────────────────────────
    assign ready_in  = 1'b1;          // MUL pipe never stalls
    assign valid_out = valid_shift[MUL_L-1];
    assign tag_out   = tag_shift[MUL_L-1];
    assign xcpt_out  = 1'b0;          // RISC-V integer MUL has no exceptions

    // ready_out is ignored because with II=1 we can't actually back-pressure
    // the pipe.  The caller is responsible for issuing only
    // when it can consume the upcoming result.
    // synthesis translate_off
    always @(posedge clk) begin
        if (rst_n && valid_out && !ready_out) begin
            // The teaching caller accepts the result after execution completes.
            // This observation does not change the datapath or handshake.
            // $display("[fu_mul] valid_out high with ready_out=0 at t=%0t", $time);
        end
    end
    // synthesis translate_on

endmodule
