// =============================================================================
// HY-RV | rv32_pmu
// Description: Instruction and cycle observation counters.
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
// rv32_pmu — RV32 Performance Monitor Unit (Stage 1 telemetry)
//

// RVM/Sscofpmf-style HPMs, with programmable event select.
//
// RISC-V priv-spec compliance (Stage 1):
//   - mcycle (64-bit), minstret (64-bit): mandatory, always counting.
//   - mhpmcounter3..(3+N_HPM-1) (64-bit): programmable via mhpmevent register.
//   - mhpmevent3..(3+N_HPM-1): selects which event the counter tracks.
//     Event 0 = disabled.  Event ID indexes into the 16-wide event bus.
//
// Interfaces:
//   - events: 16-bit pulse bus (1 = event occurred this cycle).
//     Bit assignment is P-config-specific; see p2_core.sv (or later p0/p1).
//   - event_sel[N_HPM]: 4-bit event-bus index per HPM counter.
//   - mcycle / minstret / hpm[]: 64-bit async read outputs.
//   - Write port (from CSR file): 32-bit half at a time (CSR is 32-bit XLEN).
//
// Atomicity: if wr_en and event both fire same cycle, wr_data wins; event
// is consumed (standard RISC-V behavior — csrrw replaces value).
// =============================================================================

module rv32_pmu #(
    parameter int N_EVENTS = 16,
    parameter int N_HPM    = 4      // mhpmcounter3..(2+N_HPM)
) (
    input  logic                    clk,
    input  logic                    rst_n,

    // ── Event bus (per-cycle pulses) ──
    input  logic [N_EVENTS-1:0]     events,

    // ── Event select (from mhpmevent3..N_HPM CSR, 4-bit idx; 0 = disabled) ──
    input  logic [3:0]              event_sel [N_HPM],

    // ── Counter read ports (async) ──
    output logic [63:0]             mcycle,
    output logic [63:0]             minstret,
    output logic [63:0]             hpm [N_HPM],

    // ── Counter write port ──
    //   target select: 0 = mcycle, 1 = minstret, 2..(1+N_HPM) = hpm[i]
    //   wr_hi = 0 writes low 32b, = 1 writes high 32b.
    input  logic                    wr_en,
    input  logic                    wr_hi,
    input  logic [3:0]              wr_target,
    input  logic [31:0]             wr_data
);

    // Counter storage
    logic [63:0] mcycle_r;
    logic [63:0] minstret_r;
    logic [63:0] hpm_r [N_HPM];

    // Expose async reads
    assign mcycle   = mcycle_r;
    assign minstret = minstret_r;
    always_comb begin
        for (int i = 0; i < N_HPM; i++) hpm[i] = hpm_r[i];
    end

    // Event selection per HPM (index into events bus)
    logic [N_HPM-1:0] hpm_inc;
    always_comb begin
        for (int i = 0; i < N_HPM; i++) begin
            hpm_inc[i] = (event_sel[i] != 4'd0) && events[event_sel[i]];
        end
    end

    // INSTRET event is hardwired to events[1] (convention; see p2_core).
    localparam int EVT_CYCLE   = 0;
    localparam int EVT_INSTRET = 1;

    // Sequential update
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            mcycle_r   <= 64'd0;
            minstret_r <= 64'd0;
            for (int i = 0; i < N_HPM; i++) hpm_r[i] <= 64'd0;
        end else begin
            // ── mcycle ──
            if (wr_en && wr_target == 4'd0) begin
                if (wr_hi) mcycle_r <= {wr_data, mcycle_r[31:0]};
                else       mcycle_r <= {mcycle_r[63:32], wr_data};
            end else if (events[EVT_CYCLE]) begin
                mcycle_r <= mcycle_r + 64'd1;
            end

            // ── minstret ──
            if (wr_en && wr_target == 4'd1) begin
                if (wr_hi) minstret_r <= {wr_data, minstret_r[31:0]};
                else       minstret_r <= {minstret_r[63:32], wr_data};
            end else if (events[EVT_INSTRET]) begin
                minstret_r <= minstret_r + 64'd1;
            end

            // ── HPMs ──
            for (int i = 0; i < N_HPM; i++) begin
                if (wr_en && wr_target == 4'(i + 2)) begin
                    if (wr_hi) hpm_r[i] <= {wr_data, hpm_r[i][31:0]};
                    else       hpm_r[i] <= {hpm_r[i][63:32], wr_data};
                end else if (hpm_inc[i]) begin
                    hpm_r[i] <= hpm_r[i] + 64'd1;
                end
            end
        end
    end

endmodule
