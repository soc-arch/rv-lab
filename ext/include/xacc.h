/* =============================================================================
 * HY-RV | xacc.h
 * Description: Lab 10 software API for the XACC dot-product accumulator coprocessor.
 *
 * Purpose: Computer architecture and RTL design education and lab exercises.
 * Maintained by: DSAL (Digital System Architecture Lab), Hanyang University
 * Website: https://dsa.hanyang.ac.kr
 * Supervisor: Prof. Ji-Hoon Kim (jhoonkim@hanyang.ac.kr)
 *
 * AI tools such as Codex or Claude may have assisted in creating or modifying
 * this file. See the applicable manifests and verification records for
 * file-specific provenance, revision history, and validation evidence.
 * Preserve existing license, copyright, and original author notices.
 * ============================================================================= */
#ifndef HYRV_XACC_H
#define HYRV_XACC_H

#include <stdint.h>
#include "xdot4.h"

/* Three custom-1 instructions handled by the coprocessor (ext/README.md):
 *   XACC.CLR             acc = 0                         0x0000002B
 *   XACC.DOT4 rs1, rs2   acc += dot4(rs1, rs2)           MATCH 0x0200002B MASK 0xFE007FFF
 *   XACC.RD   rd         rd = acc                        MATCH 0x0400002B MASK 0xFFFFF07F
 * acc is private 32-bit coprocessor state that wraps modulo 2^32.
 *
 * Build with EXT=xacc to emit the instructions (the lab defines HAVE_XACC).
 * Without it, a software accumulator gives the same results on any RV32IM core.
 * The asm statements are volatile: they change hidden state, so the compiler
 * must neither delete nor reorder them.
 */

#ifdef HAVE_XACC
static inline void xacc_clr(void)
{
    __asm__ volatile (".insn r CUSTOM_1, 0, 0, x0, x0, x0");
}
static inline void xacc_dot4(uint32_t a, uint32_t b)
{
    __asm__ volatile (".insn r CUSTOM_1, 0, 1, x0, %0, %1" : : "r"(a), "r"(b));
}
static inline int32_t xacc_rd(void)
{
    int32_t r;
    __asm__ volatile (".insn r CUSTOM_1, 0, 2, %0, x0, x0" : "=r"(r));
    return r;
}
#else
/* One accumulator for the whole program, like the coprocessor: a weak definition
 * in every file that includes this header is merged into a single object. */
uint32_t xacc_software_acc __attribute__((weak));
static inline void xacc_clr(void) { xacc_software_acc = 0; }
static inline void xacc_dot4(uint32_t a, uint32_t b) { xacc_software_acc += (uint32_t)xdot4_ref(a, b); }
static inline int32_t xacc_rd(void) { return (int32_t)xacc_software_acc; }
#endif

#endif
