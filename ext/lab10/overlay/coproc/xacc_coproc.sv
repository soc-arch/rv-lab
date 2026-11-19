// =============================================================================
// HY-RV | xacc_coproc
// Description: Lab 10 XACC coprocessor: a private int8 dot-product accumulator behind XIF-lite.
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

// Three custom-1 instructions (ext/README.md). Any other custom-1 word is rejected.
//
//   XACC.CLR             0000000 00000 00000 000 00000 0101011   acc = 0
//   XACC.DOT4 rs1, rs2   0000001  rs2   rs1  000 00000 0101011   acc += dot4(rs1, rs2)
//   XACC.RD   rd         0000010 00000 00000 000  rd   0101011   rd = acc
//
// acc is private 32-bit state (wraps modulo 2^32, reset to 0). It changes only
// when an accepted instruction completes (the result handshake). One instruction
// is in the coprocessor at a time. LATENCY = cycles from the issue handshake to
// result_valid (minimum 1).
module xacc_coproc #(
    parameter int unsigned LATENCY = 1
) (
    input logic clk,
    input logic rst_n,
    xif_lite_if.coproc xif_if
);
    // synthesis translate_off
    initial if (LATENCY < 1 || LATENCY > 255) $fatal(1, "xacc_coproc: LATENCY must be 1..255");
    // synthesis translate_on

    localparam logic [31:0] CLR_MATCH  = 32'h0000_002B, CLR_MASK  = 32'hFFFF_FFFF;
    localparam logic [31:0] DOT4_MATCH = 32'h0200_002B, DOT4_MASK = 32'hFE00_7FFF;
    localparam logic [31:0] RD_MATCH   = 32'h0400_002B, RD_MASK   = 32'hFFFF_F07F;

    // Provided: the same arithmetic as the Lab 09 XDOT4 unit.
    function automatic logic [31:0] dot4(input logic [31:0] a, input logic [31:0] b);
        logic signed [17:0] sum;
        sum = '0;
        for (int i = 0; i < 4; i++)
            sum = sum + 18'($signed(a[8*i +: 8]) * $signed(b[8*i +: 8]));
        return {{14{sum[17]}}, sum};
    endfunction

    // ---------------------------------------------------------------------
    // Issue: decode the offered word in the handshake cycle.
    // ---------------------------------------------------------------------
    logic is_clr, is_dot4, is_rd;
    assign is_clr  = (xif_if.issue_insn & CLR_MASK)  == CLR_MATCH;
    assign is_dot4 = (xif_if.issue_insn & DOT4_MASK) == DOT4_MATCH;
    assign is_rd   = (xif_if.issue_insn & RD_MASK)   == RD_MATCH;

    logic busy_r;                 // an accepted instruction has not completed yet
    logic [7:0] count_r;          // cycles left until result_valid
    logic op_clr_r, op_dot4_r, op_rd_r;
    logic [31:0] rs1_r, rs2_r;    // operands captured at acceptance
    logic [31:0] acc_r;           // private architectural state

    assign xif_if.issue_ready = !busy_r;   // one instruction at a time
    // TODO(lab10-1): accept exactly the three XACC encodings; reject every other word.
    //   A rejected word becomes an illegal-instruction trap in the core.
    assign xif_if.issue_accept    = 1'b0;
    // TODO(lab10-2): promise a register write only for the instruction that writes rd.
    assign xif_if.issue_writeback = 1'b0;

    logic issue_fire, result_fire;
    assign issue_fire  = xif_if.issue_valid && xif_if.issue_ready && xif_if.issue_accept;

    // ---------------------------------------------------------------------
    // Result: registered, held until the core takes it.
    // ---------------------------------------------------------------------
    assign xif_if.result_valid = busy_r && (count_r == 8'd0);
    // TODO(lab10-4): return acc for XACC.RD and set result_we only for XACC.RD.
    //   result_we must equal the issue_writeback promise for the same instruction.
    assign xif_if.result_data  = 32'd0;
    assign xif_if.result_we    = 1'b0;
    assign result_fire = xif_if.result_valid && xif_if.result_ready;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            busy_r <= 1'b0;
            count_r <= 8'd0;
            {op_clr_r, op_dot4_r, op_rd_r} <= 3'b000;
            rs1_r <= 32'd0;
            rs2_r <= 32'd0;
            acc_r <= 32'd0;
        end else begin
            if (issue_fire) begin
                busy_r <= 1'b1;
                count_r <= 8'(LATENCY - 1);
                {op_clr_r, op_dot4_r, op_rd_r} <= {is_clr, is_dot4, is_rd};
                rs1_r <= xif_if.issue_rs1;
                rs2_r <= xif_if.issue_rs2;
            end else if (busy_r && count_r != 8'd0) begin
                count_r <= count_r - 8'd1;
            end
            if (result_fire) begin
                busy_r <= 1'b0;
                // TODO(lab10-3): update acc when the instruction completes.
                //   XACC.CLR clears acc; XACC.DOT4 adds dot4(rs1_r, rs2_r); XACC.RD keeps it.
            end
        end
    end

    // synthesis translate_off
    always @(posedge clk) if (rst_n) begin
        assert (!(issue_fire && result_fire)) else $fatal(1, "xacc: issue during an unfinished instruction");
        assert ($onehot0({is_clr, is_dot4, is_rd})) else $fatal(1, "xacc: overlapping encodings");
    end
    // synthesis translate_on
endmodule
