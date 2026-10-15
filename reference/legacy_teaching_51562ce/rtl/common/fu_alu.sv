// Local editable teaching snapshot; see SOURCE_SNAPSHOT.json for provenance.
// =============================================================================
// fu_alu — RV32I ALU (HY-RV FU pool member)
//
// 11 ops: ADD / SUB / AND / OR / XOR / SLL / SRL / SRA / SLT / SLTU / PASS_B.
// AGU (address generation for LD/ST) is absorbed as the ADD mode — no
// separate module.  The caller selects ADD for an effective-address sum.
//
// Latency / throughput:
//   L  = 0   (valid_in and valid_out on the same cycle)
//   II = 1
//
// Request/response ports carry operation, operands, validity and tag.
// ready_in is unconditionally 1; unused handshake fields can be tied to
// constants by a caller that uses the combinational result directly.
//
// ALU op encoding (`alu_op[3:0]`) is shared with the teaching backend:
//   ADD=0 · SUB=1 · AND=2 · OR=3 · XOR=4 · SLL=5 · SRL=6 · SRA=7 ·
//   SLT=8 · SLTU=9 · PASS_B=10 (used by LUI)
// =============================================================================

module fu_alu #(
    parameter int XLEN  = 32,
    parameter int TAG_W = 3
) (
    input  logic                 clk,    // unused (L=0) but kept for interface uniformity
    input  logic                 rst_n,  // unused

    // Request
    input  logic [3:0]           op,
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

    localparam logic [3:0] ALU_ADD    = 4'd0;
    localparam logic [3:0] ALU_SUB    = 4'd1;
    localparam logic [3:0] ALU_AND    = 4'd2;
    localparam logic [3:0] ALU_OR     = 4'd3;
    localparam logic [3:0] ALU_XOR    = 4'd4;
    localparam logic [3:0] ALU_SLL    = 4'd5;
    localparam logic [3:0] ALU_SRL    = 4'd6;
    localparam logic [3:0] ALU_SRA    = 4'd7;
    localparam logic [3:0] ALU_SLT    = 4'd8;
    localparam logic [3:0] ALU_SLTU   = 4'd9;
    localparam logic [3:0] ALU_PASS_B = 4'd10;

    always_comb begin
        case (op)
            ALU_ADD:    result = operand_a + operand_b;
            ALU_SUB:    result = operand_a - operand_b;
            ALU_AND:    result = operand_a & operand_b;
            ALU_OR:     result = operand_a | operand_b;
            ALU_XOR:    result = operand_a ^ operand_b;
            ALU_SLL:    result = operand_a << operand_b[4:0];
            ALU_SRL:    result = operand_a >> operand_b[4:0];
            ALU_SRA:    result = $signed(operand_a) >>> operand_b[4:0];
            ALU_SLT:    result = {{(XLEN-1){1'b0}}, $signed(operand_a) < $signed(operand_b)};
            ALU_SLTU:   result = {{(XLEN-1){1'b0}}, operand_a < operand_b};
            ALU_PASS_B: result = operand_b;
            default:    result = '0;
        endcase
    end

    // L=0: valid_out follows valid_in combinationally, tag passes through.
    assign ready_in  = 1'b1;
    assign valid_out = valid_in;
    assign tag_out   = tag_in;
    assign xcpt_out  = 1'b0;

    // ready_out is ignored by this combinational unit — a consumer that
    // cannot accept must back-pressure upstream of valid_in.  Keeping the
    // port makes fu_alu drop-in swappable with fu_mul / fu_div / fu_div's
    // higher-latency functional units using the same request/response boundary.

    // Suppress "unused" lint on clk/rst_n — they exist only for interface
    // uniformity with pipelined / multi-cycle pool members.
    // verilator lint_off UNUSED
    wire _unused_ok = &{1'b0, clk, rst_n, ready_out, 1'b0};
    // verilator lint_on UNUSED

endmodule
