/* =============================================================================
 * HY-RV | xdot4.h
 * Description: Lab 09 software API for the XDOT4 custom instruction.
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
#ifndef HYRV_XDOT4_H
#define HYRV_XDOT4_H

#include <stdint.h>

/* XDOT4 rd, rs1, rs2 (custom-0, funct3=0, funct7=1; MATCH 0x0200000B, MASK 0xFE00707F)
 *   rd = rs1.byte0*rs2.byte0 + rs1.byte1*rs2.byte1 + rs1.byte2*rs2.byte2 + rs1.byte3*rs2.byte3
 * Each byte is a signed int8; byte 0 is bits 7:0. The sum is sign-extended to 32 bits.
 *
 * Build with EXT=xdot4 to emit the instruction (the lab defines HAVE_XDOT4).
 * Build with EXT=sw to run the same API as portable C on any RV32IM core.
 */

/* Portable reference. Tests use it as the golden model for the instruction. */
static inline int32_t xdot4_ref(uint32_t a, uint32_t b)
{
    int32_t sum = 0;
    for (unsigned i = 0; i < 4; ++i)
        sum += (int32_t)(int8_t)(a >> (8 * i)) * (int32_t)(int8_t)(b >> (8 * i));
    return sum;
}

static inline int32_t xdot4(uint32_t a, uint32_t b)
{
#ifdef HAVE_XDOT4
    int32_t r;
    /* .insn r opcode, funct3, funct7, rd, rs1, rs2 -- the assembler builds the word. */
    __asm__ (".insn r CUSTOM_0, 0, 1, %0, %1, %2" : "=r"(r) : "r"(a), "r"(b));
    return r;
#else
    return xdot4_ref(a, b);
#endif
}

#endif
