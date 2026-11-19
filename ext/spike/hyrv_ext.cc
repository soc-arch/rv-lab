// =============================================================================
// HY-RV | hyrv_ext
// Description: Spike reference model for the Lab 09 XDOT4 and Lab 10 XACC extensions.
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

// Loaded with: spike --extlib=libhyrv_ext.so --extension=hyrv_xdot4 (Lab 09)
//          or: spike --extlib=libhyrv_ext.so --extension=hyrv_xacc  (Lab 10)
// Each extension registers exactly the instructions of its lab core, so Spike
// and the RTL implement the same ISA. This file is written from ext/README.md,
// independently of the RTL. Every encoding that is not listed below keeps
// Spike's illegal-instruction trap.
//
//   XDOT4     custom-0  MATCH 0x0200000B  MASK 0xFE00707F
//             rd = sext32( sum_{i=0..3} int8(rs1.byte[i]) * int8(rs2.byte[i]) )
//   XACC.CLR  custom-1  MATCH 0x0000002B  MASK 0xFFFFFFFF   acc = 0
//   XACC.DOT4 custom-1  MATCH 0x0200002B  MASK 0xFE007FFF   acc += dot4(rs1, rs2)
//   XACC.RD   custom-1  MATCH 0x0400002B  MASK 0xFFFFF07F   rd = acc
//
// acc is 32 bits and wraps modulo 2^32. Reset sets acc to zero.

#include "extension.h"
#include <cstdint>

namespace {

constexpr const char *kXdot4 = "hyrv_xdot4";
constexpr const char *kXacc = "hyrv_xacc";

int32_t dot4(uint32_t a, uint32_t b) {
    int32_t sum = 0;
    for (int i = 0; i < 4; ++i) {
        const int32_t x = static_cast<int8_t>(static_cast<uint8_t>(a >> (8 * i)));
        const int32_t y = static_cast<int8_t>(static_cast<uint8_t>(b >> (8 * i)));
        sum += x * y;  // |sum| <= 65,536: no 32-bit overflow.
    }
    return sum;
}

class xdot4_extension_t : public extension_t {
public:
    const char *name() const override { return kXdot4; }
    std::vector<insn_desc_t> get_instructions(const processor_t &) override;
    std::vector<disasm_insn_t *> get_disasms(const processor_t *) override { return {}; }
};

class xacc_extension_t : public extension_t {
public:
    uint32_t acc = 0;  // private coprocessor state

    const char *name() const override { return kXacc; }
    void reset(processor_t &) override { acc = 0; }
    std::vector<insn_desc_t> get_instructions(const processor_t &) override;
    std::vector<disasm_insn_t *> get_disasms(const processor_t *) override { return {}; }
};

xacc_extension_t *self(processor_t *p) {
    return static_cast<xacc_extension_t *>(p->get_extension(kXacc));
}

uint32_t xreg(processor_t *p, unsigned index) {
    return static_cast<uint32_t>(p->get_state()->XPR[index]);
}

void write_rd(processor_t *p, insn_t insn, uint32_t value) {
    // RV32 Spike keeps integer registers sign-extended to 64 bits.
    const reg_t extended = static_cast<reg_t>(static_cast<int64_t>(static_cast<int32_t>(value)));
    state_t *state = p->get_state();
    state->log_reg_write[insn.rd() << 4] = {extended, 0};
    state->XPR.write(insn.rd(), extended);
}

reg_t xdot4(processor_t *p, insn_t insn, reg_t pc) {
    write_rd(p, insn, static_cast<uint32_t>(dot4(xreg(p, insn.rs1()), xreg(p, insn.rs2()))));
    return pc + 4;
}

reg_t xacc_clr(processor_t *p, insn_t, reg_t pc) {
    self(p)->acc = 0;
    return pc + 4;
}

reg_t xacc_dot4(processor_t *p, insn_t insn, reg_t pc) {
    xacc_extension_t *ext = self(p);
    ext->acc += static_cast<uint32_t>(dot4(xreg(p, insn.rs1()), xreg(p, insn.rs2())));
    return pc + 4;
}

reg_t xacc_rd(processor_t *p, insn_t insn, reg_t pc) {
    write_rd(p, insn, self(p)->acc);
    return pc + 4;
}

insn_desc_t describe(insn_bits_t match, insn_bits_t mask, insn_func_t f) {
    return insn_desc_t{match, mask, f, f, f, f, f, f, f, f};
}

std::vector<insn_desc_t> xdot4_extension_t::get_instructions(const processor_t &) {
    return {describe(0x0200000B, 0xFE00707F, &xdot4)};
}

std::vector<insn_desc_t> xacc_extension_t::get_instructions(const processor_t &) {
    return {
        describe(0x0000002B, 0xFFFFFFFF, &xacc_clr),
        describe(0x0200002B, 0xFE007FFF, &xacc_dot4),
        describe(0x0400002B, 0xFFFFF07F, &xacc_rd),
    };
}

}  // namespace

REGISTER_EXTENSION(hyrv_xdot4, []() { return new xdot4_extension_t; })
REGISTER_EXTENSION(hyrv_xacc, []() { return new xacc_extension_t; })
