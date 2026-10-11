// Local editable teaching snapshot; see SOURCE_SNAPSHOT.json for provenance.
// =============================================================================
// rv32_csr — RV32I M-mode CSR file + trap controller + PMU integration
//

// architectural M-mode CSR state + trap write-path + mret read-path +
// rv32_pmu instance.
//
// RISC-V priv-spec compliance (Stage 1 — M-mode only):
//   Read-only ident CSRs (hardwired 0):
//     mvendorid (0xF11), marchid (0xF12), mimpid (0xF13), mhartid (0xF14)
//     misa (0x301) = { MXL=01 (32b), 000000...I+M bits set }
//   Read/write M-mode CSRs (Stage 1):
//     mstatus  (0x300) — only MIE/MPIE/MPP fields maintained; rest WPRI/zero
//     mie      (0x304) — readable/writable (no interrupts implemented yet)
//     mtvec    (0x305) — base + mode (mode=0 direct only; mode=1 deferred)
//     mscratch (0x340)
//     mepc     (0x341)
//     mcause   (0x342)
//     mtval    (0x343)
//     mip      (0x344) — readable/writable (tied low until interrupts)
//   Counter CSRs (delegated to rv32_pmu):
//     mcycle (0xB00) / mcycleh (0xB80)
//     minstret (0xB02) / minstreth (0xB82)
//     mhpmcounter3..6 (0xB03..0xB06) / high (0xB83..0xB86)
//     mhpmevent3..6 (0x323..0x326) — programmable event select
//   URO mirrors (optional for U-mode; Stage 1 skip):
//     cycle / cycleh / instret / instreth / time — deferred.
//
// Trap causes supported (Stage 1):
//   cause=2: Illegal instruction (unknown opcode, illegal CSR, WARL violation)
//   cause=11: Environment call from M-mode (ECALL)
//   cause=3: Breakpoint (EBREAK)
//
// Interface notes:
//   - CSR access: purely combinational read (csr_rdata valid same cycle as
//     csr_access).  Write happens at posedge clk.
//   - Trap control: `trap_take_i` from core asserts one cycle to commit a
//     trap event (update mepc/mcause/mtval/mstatus.MPIE/MIE).
//   - mret: `mret_take_i` one cycle to restore mstatus (MPIE→MIE).
//   - Outputs for core: trap_vector (= mtvec base), mret_target (= mepc).
// =============================================================================

module rv32_csr #(
    parameter int N_HPM    = 4,
    parameter int N_EVENTS = 16
) (
    input  logic                    clk,
    input  logic                    rst_n,

    // ─── Core-side CSR access (combinational read, sync write) ────────
    input  logic                    csr_access_i,   // 1 = valid CSR access this cycle
    input  logic [11:0]             csr_addr_i,
    input  logic [2:0]              csr_funct3_i,   // 001..011 = rw/rs/rc; 101..111 = imm variants
    input  logic [4:0]              csr_uimm_i,     // rs1 field (imm for 10x/11x, rs1 addr for 01x)
    input  logic [31:0]             csr_rs1_data_i, // rs1 value (ignored for imm variants)
    output logic [31:0]             csr_rdata_o,
    output logic                    csr_illegal_o,  // 1 if access should trap

    // ─── Trap commit (one-cycle pulse from core) ──────────────────────
    input  logic                    trap_take_i,
    input  logic                    trap_is_irq_i,  // 1 = interrupt (mcause[31]=1), 0 = exception
    input  logic [30:0]             trap_cause_i,   // cause[30:0]
    input  logic [31:0]             trap_epc_i,     // PC to save into mepc
    input  logic [31:0]             trap_tval_i,
    input  logic                    mret_take_i,
    output logic [31:0]             trap_vector_o,  // where IF should redirect on trap
    output logic [31:0]             mret_target_o,  // where IF should redirect on mret

    // ─── External IRQ lines (SoC → core) ───────────────────────────────
    //   Levels held by external IRQ controller (CLINT/PLIC/CLIC).  Core
    //   samples these each cycle into mip live bits.
    input  logic                    irq_software_i,  // MSIP (from CLINT.msip MMIO)
    input  logic                    irq_timer_i,     // MTIP (from CLINT mtime ≥ mtimecmp)
    input  logic                    irq_external_i,  // MEIP (from PLIC / external)

    // ─── Pending-interrupt signal to core (for trap-take decision) ─────
    //   Asserted when any enabled M-mode IRQ is pending AND mstatus.MIE=1.
    output logic                    irq_pending_o,
    output logic [3:0]              irq_cause_o,     // encoded cause (3=MSI, 7=MTI, 11=MEI)

    // ─── Event bus (for PMU) ──────────────────────────────────────────
    input  logic [N_EVENTS-1:0]     events_i
);

    // ─── Identifier CSRs (read-only, hardwired) ──
    localparam logic [31:0] MISA_VAL =
        (32'b01 << 30) |               // MXL = 01 (RV32)
        (1 << 8)  |                    // I
        (1 << 12);                     // M

    // ─── M-mode architectural state ──
    // mstatus fields: MIE (bit 3), MPIE (7), MPP (12:11).  Stage 1: MPP=11 (M).
    logic        mstatus_mie;
    logic        mstatus_mpie;
    logic [1:0]  mstatus_mpp;

    // mie R/W; mip mostly derived from external IRQ lines (live bits).
    //   Standard bits: MSIP[3], MTIP[7], MEIP[11].  Other bits reserved (0).
    logic [31:0] mie_r;
    logic [31:0] mip_live;   // Live-sampled from external IRQ pins

    logic [31:0] mtvec_r;     // {base[29:0], mode[1:0]}; mode=0 direct
    logic [31:0] mscratch_r;
    logic [31:0] mepc_r;      // low 2 bits always 0
    logic [31:0] mcause_r;
    logic [31:0] mtval_r;

    // ─── HPM event selects (mhpmevent3..6) ──
    logic [3:0]  hpmevent_r [N_HPM];

    // ─── PMU counter read-back ──
    logic [63:0] mcycle_q;
    logic [63:0] minstret_q;
    logic [63:0] hpm_q [N_HPM];

    // ─── PMU write-through (from CSR writes to counter CSRs) ──
    logic        pmu_wr_en;
    logic        pmu_wr_hi;
    logic [3:0]  pmu_wr_target;
    logic [31:0] pmu_wr_data;

    rv32_pmu #(
        .N_EVENTS (N_EVENTS),
        .N_HPM    (N_HPM)
    ) u_pmu (
        .clk        (clk),
        .rst_n      (rst_n),
        .events     (events_i),
        .event_sel  (hpmevent_r),
        .mcycle     (mcycle_q),
        .minstret   (minstret_q),
        .hpm        (hpm_q),
        .wr_en      (pmu_wr_en),
        .wr_hi      (pmu_wr_hi),
        .wr_target  (pmu_wr_target),
        .wr_data    (pmu_wr_data)
    );

    // ═════════════════════════════════════════════════════════════════════
    // CSR address decoding + read data mux
    // ═════════════════════════════════════════════════════════════════════

    // Returns read value + "known" flag.  Unknown addresses → illegal.
    logic [31:0] rdata;
    logic        addr_known;

    // Distinguish writable (for read) vs read-only writes (those would trap).
    logic        addr_readonly;

    always_comb begin
        rdata         = 32'd0;
        addr_known    = 1'b1;
        addr_readonly = 1'b0;

        unique case (csr_addr_i)
            12'hF11: begin rdata = 32'd0;                        addr_readonly = 1'b1; end // mvendorid
            12'hF12: begin rdata = 32'd0;                        addr_readonly = 1'b1; end // marchid
            12'hF13: begin rdata = 32'd0;                        addr_readonly = 1'b1; end // mimpid
            12'hF14: begin rdata = 32'd0;                        addr_readonly = 1'b1; end // mhartid
            12'h301: begin rdata = MISA_VAL;                     addr_readonly = 1'b1; end // misa (WARL; Stage 1 RO)
            12'h300: begin                                         // mstatus
                rdata = 32'b0;
                rdata[3]      = mstatus_mie;
                rdata[7]      = mstatus_mpie;
                rdata[12:11]  = mstatus_mpp;
            end
            12'h304: rdata = mie_r;
            12'h305: rdata = mtvec_r;
            12'h340: rdata = mscratch_r;
            12'h341: rdata = mepc_r;
            12'h342: rdata = mcause_r;
            12'h343: rdata = mtval_r;
            12'h344: rdata = mip_live;
            // Counter CSRs (delegated to PMU read-back)
            12'hB00: rdata = mcycle_q[31:0];                     // mcycle
            12'hB80: rdata = mcycle_q[63:32];                    // mcycleh
            12'hB02: rdata = minstret_q[31:0];                   // minstret
            12'hB82: rdata = minstret_q[63:32];                  // minstreth
            12'hB03: rdata = hpm_q[0][31:0];                     // mhpmcounter3
            12'hB04: rdata = hpm_q[1][31:0];
            12'hB05: rdata = hpm_q[2][31:0];
            12'hB06: rdata = hpm_q[3][31:0];
            12'hB83: rdata = hpm_q[0][63:32];                    // mhpmcounter3h
            12'hB84: rdata = hpm_q[1][63:32];
            12'hB85: rdata = hpm_q[2][63:32];
            12'hB86: rdata = hpm_q[3][63:32];
            12'h323: rdata = {28'b0, hpmevent_r[0]};             // mhpmevent3 (low 4b used)
            12'h324: rdata = {28'b0, hpmevent_r[1]};
            12'h325: rdata = {28'b0, hpmevent_r[2]};
            12'h326: rdata = {28'b0, hpmevent_r[3]};
            // User-read-only counter mirrors.  The architecture permits
            // unprivileged reads when mcounteren bit is set; Stage 1
            // just returns the same value as the M-mode counter.
            12'hC00: begin rdata = mcycle_q[31:0];                addr_readonly = 1'b1; end // cycle
            12'hC80: begin rdata = mcycle_q[63:32];               addr_readonly = 1'b1; end // cycleh
            12'hC02: begin rdata = minstret_q[31:0];              addr_readonly = 1'b1; end // instret
            12'hC82: begin rdata = minstret_q[63:32];             addr_readonly = 1'b1; end // instreth
            12'hC01: begin rdata = mcycle_q[31:0];                addr_readonly = 1'b1; end // time (mirror)
            12'hC81: begin rdata = mcycle_q[63:32];               addr_readonly = 1'b1; end // timeh
            default: begin
                rdata      = 32'd0;
                addr_known = 1'b0;
            end
        endcase
    end

    assign csr_rdata_o = rdata;

    // ═════════════════════════════════════════════════════════════════════
    // Write data computation — csrrw/rs/rc/rwi/rsi/rci semantics
    // ═════════════════════════════════════════════════════════════════════
    // funct3:
    //   001 RW : new = src                         (if rd=x0, read suppressed — handled by core)
    //   010 RS : new = rdata | src                 (if rs1=x0, no write)
    //   011 RC : new = rdata & ~src                (if rs1=x0, no write)
    //   101 RWI: new = uimm                        (rd=x0: read suppressed)
    //   110 RSI: new = rdata | uimm                (uimm=0: no write)
    //   111 RCI: new = rdata & ~uimm               (uimm=0: no write)
    //
    // "no-write" per spec: no side effect, no access exception on RO CSRs.
    logic [31:0] src;
    logic        is_imm;
    logic        write_performed;    // 1 = this access performs an architectural write
    logic [31:0] wdata_final;

    assign is_imm = csr_funct3_i[2];
    assign src    = is_imm ? {27'b0, csr_uimm_i} : csr_rs1_data_i;

    always_comb begin
        // Default
        wdata_final     = rdata;
        write_performed = 1'b0;
        unique case (csr_funct3_i)
            3'b001, 3'b101: begin                        // CSRRW / CSRRWI
                wdata_final     = src;
                write_performed = 1'b1;
            end
            3'b010, 3'b110: begin                        // CSRRS / CSRRSI
                wdata_final     = rdata | src;
                write_performed = (is_imm ? (csr_uimm_i != 5'd0)
                                          : (csr_uimm_i != 5'd0));  // rs1 field = uimm slot
            end
            3'b011, 3'b111: begin                        // CSRRC / CSRRCI
                wdata_final     = rdata & ~src;
                write_performed = (csr_uimm_i != 5'd0);
            end
            default: begin
                wdata_final     = rdata;
                write_performed = 1'b0;
            end
        endcase
    end

    // Illegal CSR access:
    //   - Unknown address
    //   - Write attempted to read-only CSR
    //   Stage 1 skips privilege check (only M-mode exists).
    assign csr_illegal_o = csr_access_i && (~addr_known || (write_performed && addr_readonly));

    // ═════════════════════════════════════════════════════════════════════
    // mip live bits + pending IRQ detection
    //   MSIP=3, MTIP=7, MEIP=11 (per RISC-V Priv Spec Table 3.6).
    //   mie read/write is standard; mip read returns live.
    // ═════════════════════════════════════════════════════════════════════
    always_comb begin
        mip_live       = 32'd0;
        mip_live[3]    = irq_software_i;
        mip_live[7]    = irq_timer_i;
        mip_live[11]   = irq_external_i;
    end

    // Pending-enabled IRQs (global MIE gate at core side — we output the
    // "would-trap" signal here).  RISC-V priority: MEI > MSI > MTI (per
    // Priv Spec §3.1.9 "Interrupt priority").
    logic [31:0] mip_and_mie;
    assign mip_and_mie = mip_live & mie_r;
    always_comb begin
        irq_pending_o = mstatus_mie & (|mip_and_mie);
        // Priority encoding (RISC-V standard: MEI > MSI > MTI)
        if (mip_and_mie[11])      irq_cause_o = 4'd11;
        else if (mip_and_mie[3])  irq_cause_o = 4'd3;
        else if (mip_and_mie[7])  irq_cause_o = 4'd7;
        else                      irq_cause_o = 4'd0;
    end

    // ═════════════════════════════════════════════════════════════════════
    // Sequential state update
    //   Priority: reset > trap_take > mret_take > csr_write.
    //   PMU counter CSRs route through u_pmu's wr port; others updated here.
    // ═════════════════════════════════════════════════════════════════════

    logic        csr_write_fire;
    assign csr_write_fire = csr_access_i && write_performed && addr_known && !addr_readonly
                          && !trap_take_i && !mret_take_i;

    // PMU write port
    always_comb begin
        pmu_wr_en     = 1'b0;
        pmu_wr_hi     = 1'b0;
        pmu_wr_target = 4'd0;
        pmu_wr_data   = wdata_final;

        if (csr_write_fire) begin
            unique case (csr_addr_i)
                12'hB00: begin pmu_wr_en = 1'b1; pmu_wr_target = 4'd0; pmu_wr_hi = 1'b0; end
                12'hB80: begin pmu_wr_en = 1'b1; pmu_wr_target = 4'd0; pmu_wr_hi = 1'b1; end
                12'hB02: begin pmu_wr_en = 1'b1; pmu_wr_target = 4'd1; pmu_wr_hi = 1'b0; end
                12'hB82: begin pmu_wr_en = 1'b1; pmu_wr_target = 4'd1; pmu_wr_hi = 1'b1; end
                12'hB03: begin pmu_wr_en = 1'b1; pmu_wr_target = 4'd2; pmu_wr_hi = 1'b0; end
                12'hB83: begin pmu_wr_en = 1'b1; pmu_wr_target = 4'd2; pmu_wr_hi = 1'b1; end
                12'hB04: begin pmu_wr_en = 1'b1; pmu_wr_target = 4'd3; pmu_wr_hi = 1'b0; end
                12'hB84: begin pmu_wr_en = 1'b1; pmu_wr_target = 4'd3; pmu_wr_hi = 1'b1; end
                12'hB05: begin pmu_wr_en = 1'b1; pmu_wr_target = 4'd4; pmu_wr_hi = 1'b0; end
                12'hB85: begin pmu_wr_en = 1'b1; pmu_wr_target = 4'd4; pmu_wr_hi = 1'b1; end
                12'hB06: begin pmu_wr_en = 1'b1; pmu_wr_target = 4'd5; pmu_wr_hi = 1'b0; end
                12'hB86: begin pmu_wr_en = 1'b1; pmu_wr_target = 4'd5; pmu_wr_hi = 1'b1; end
                default: ;
            endcase
        end
    end

    // Non-PMU CSR sequential write (+ trap / mret)
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            mstatus_mie    <= 1'b0;
            mstatus_mpie   <= 1'b0;
            mstatus_mpp    <= 2'b11;    // default to M-mode
            mie_r          <= 32'd0;
            mtvec_r        <= 32'd0;
            mscratch_r     <= 32'd0;
            mepc_r         <= 32'd0;
            mcause_r       <= 32'd0;
            mtval_r        <= 32'd0;
            for (int i = 0; i < N_HPM; i++) hpmevent_r[i] <= 4'd0;
        end else begin
            // ── Trap commit ──
            if (trap_take_i) begin
                mepc_r       <= {trap_epc_i[31:2], 2'b00};   // IALIGN=32, low 2 bits zeroed
                mcause_r     <= {trap_is_irq_i, trap_cause_i};
                mtval_r      <= trap_tval_i;
                mstatus_mpie <= mstatus_mie;
                mstatus_mie  <= 1'b0;
                mstatus_mpp  <= 2'b11;
            end

            // ── mret ──
            else if (mret_take_i) begin
                mstatus_mie  <= mstatus_mpie;
                mstatus_mpie <= 1'b1;
                mstatus_mpp  <= 2'b11;
            end

            // ── CSR write path (lowest priority) ──
            else if (csr_write_fire) begin
                unique case (csr_addr_i)
                    12'h300: begin                       // mstatus
                        mstatus_mie  <= wdata_final[3];
                        mstatus_mpie <= wdata_final[7];
                        mstatus_mpp  <= wdata_final[12:11];
                    end
                    12'h304: mie_r        <= wdata_final;
                    12'h305: mtvec_r      <= {wdata_final[31:2], 2'b00};  // mode=0 direct
                    12'h340: mscratch_r   <= wdata_final;
                    12'h341: mepc_r       <= {wdata_final[31:2], 2'b00};
                    12'h342: mcause_r     <= wdata_final;
                    12'h343: mtval_r      <= wdata_final;
                    12'h344: /* mip live; writes ignored Stage 1 */;
                    12'h323: hpmevent_r[0] <= wdata_final[3:0];
                    12'h324: hpmevent_r[1] <= wdata_final[3:0];
                    12'h325: hpmevent_r[2] <= wdata_final[3:0];
                    12'h326: hpmevent_r[3] <= wdata_final[3:0];
                    default: ; // PMU counter CSRs handled via u_pmu
                endcase
            end
        end
    end

    // ─── Redirect targets ──
    //   mode=0 direct: vector = mtvec base (mtvec[31:2] << 2).
    assign trap_vector_o = {mtvec_r[31:2], 2'b00};
    assign mret_target_o = mepc_r;

endmodule
