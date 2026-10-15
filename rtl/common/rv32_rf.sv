// =============================================================================
// HY-RV | rv32_rf
// Description: Integer register file with architectural x0 behavior.
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
// rv32_rf — RV32 32×32-bit Register File
//


//



// SYNC_READ=0).
//
// - 2 read ports (rs1, rs2):
//     SYNC_READ=0 → combinational (async).  x0 read returns 0.  P0/P1/P2.


// - 1 write port (rd, wb_data): synchronous on posedge clk.  x0 write ignored.
// - Reset: all regs → 0.
//
// ── Write-before-read semantic (WB_FORWARD) ──
//





//






//   - P3 (8-stage IF1/IF2/ID/RR/EX/MEM1/MEM2/WB): WB→RR same-cycle write fwd



//







//

// rf_mode_decision.md.
// =============================================================================

module rv32_rf #(
    parameter bit WB_FORWARD = 1'b1,
    parameter bit SYNC_READ  = 1'b0
) (
    input  logic        clk,
    input  logic        rst_n,

    // Read port 0
    input  logic [4:0]  rs1_addr,
    output logic [31:0] rs1_data,

    // Read port 1
    input  logic [4:0]  rs2_addr,
    output logic [31:0] rs2_data,

    // Write port
    input  logic        wb_en,
    input  logic [4:0]  wb_addr,
    input  logic [31:0] wb_data
);

    logic [31:0] rf [0:31];

    // ── Read port datapath ──
    generate
        if (SYNC_READ) begin : g_sync


            //



            //

            // read result = 0.

            logic [31:0] rs1_data_q, rs2_data_q;

            always_ff @(posedge clk or negedge rst_n) begin
                if (!rst_n) begin
                    rs1_data_q <= 32'h0;
                    rs2_data_q <= 32'h0;
                end else begin
                    rs1_data_q <= (rs1_addr == 5'd0) ? 32'h0 : rf[rs1_addr];
                    rs2_data_q <= (rs2_addr == 5'd0) ? 32'h0 : rf[rs2_addr];
                end
            end

            assign rs1_data = rs1_data_q;
            assign rs2_data = rs2_data_q;

            // Suppress lint on unused WB_FORWARD parameter when SYNC_READ=1.
            // verilator lint_off UNUSED
            wire _unused_wbf_sync = WB_FORWARD;
            // verilator lint_on UNUSED
        end else begin : g_async

            if (WB_FORWARD) begin : g_wb_fwd
                logic wb_to_rs1, wb_to_rs2;
                assign wb_to_rs1 = wb_en && (wb_addr != 5'd0) && (wb_addr == rs1_addr);
                assign wb_to_rs2 = wb_en && (wb_addr != 5'd0) && (wb_addr == rs2_addr);

                assign rs1_data = (rs1_addr == 5'd0) ? 32'h0 :
                                  wb_to_rs1           ? wb_data :
                                                        rf[rs1_addr];
                assign rs2_data = (rs2_addr == 5'd0) ? 32'h0 :
                                  wb_to_rs2           ? wb_data :
                                                        rf[rs2_addr];
            end else begin : g_no_fwd
                assign rs1_data = (rs1_addr == 5'd0) ? 32'h0 : rf[rs1_addr];
                assign rs2_data = (rs2_addr == 5'd0) ? 32'h0 : rf[rs2_addr];
            end
        end
    endgenerate


    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (int i = 0; i < 32; i++) rf[i] <= 32'h0;
        end else if (wb_en && wb_addr != 5'd0) begin
            rf[wb_addr] <= wb_data;
        end
    end

endmodule
