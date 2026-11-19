/* =============================================================================
 * HY-RV | ext_xdot4
 * Description: Directed Lab 09 test: XDOT4 results, register forms, dependences and illegal neighbours.
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
/* Run: make ext-test EXT=xdot4 RTL_DIR=$PWD/student/lab09/rtl
 * Expected values in section 1 are constants worked out by hand (ext/README.md),
 * independent of both xdot4_ref() and the hardware. */
#include "lab.h"
#include "stdio.h"
#include "xdot4.h"
#include "ext_trap.h"

#ifndef HAVE_XDOT4
#error "Build this test with EXT=xdot4"
#endif

static uint32_t lcg_state = 0x2026u;
static uint32_t lcg(void) { lcg_state = lcg_state * 1664525u + 1013904223u; return lcg_state; }

static const struct { uint32_t a, b, expected; } vectors[] = {
    {0x04030201u, 0x08070605u, 70u},                    /* 5+12+21+32 */
    {0xFC03FE01u, 0x02FF0403u, (uint32_t)-16},          /* 3-8-3-8 */
    {0x80808080u, 0x80808080u, 65536u},                 /* largest sum */
    {0x80808080u, 0x7F7F7F7Fu, (uint32_t)-65024},       /* smallest sum */
    {0x7F7F7F7Fu, 0x7F7F7F7Fu, 64516u},                 /* 4 * 127 * 127 */
    {0xFFFFFFFFu, 0xFFFFFFFFu, 4u},                     /* (-1)*(-1) * 4 */
    {0x000000FFu, 0x00000080u, 128u},                   /* (-1)*(-128), byte 0 only */
    {0x12000000u, 0xF6000000u, (uint32_t)-180},         /* 18*(-10), byte 3 only */
};

int main(void)
{
    ext_trap_install();
    ext_irq_enable();

    /* 1. Hand-computed vectors: checks 1..8. */
    for (unsigned i = 0; i < sizeof vectors / sizeof vectors[0]; ++i)
        lab_check(1 + i, (uint32_t)xdot4(vectors[i].a, vectors[i].b), vectors[i].expected);

    /* 2. 512 pseudo-random pairs against the portable C reference: check 20. */
    uint32_t mismatches = 0, checksum = 0;
    for (unsigned i = 0; i < 512; ++i) {
        uint32_t a = lcg(), b = lcg();
        int32_t got = xdot4(a, b);
        mismatches += got != xdot4_ref(a, b);
        checksum = checksum * 31u + (uint32_t)got;
    }
    lab_check(20, mismatches, 0);
    lab_result(0, checksum);

    /* 3. Register forms (checks 21..23): rd==rs1==rs2, the exact word from the
     *    slides (xdot4 a0, a0, a1 = 0x02B5050B), and rd = x0 (no trap, no write). */
    {
        uint32_t x = 0x04030201u, y = 0x08070605u, r;
        __asm__ volatile ("mv a0, %1\n .insn r CUSTOM_0, 0, 1, a0, a0, a0\n mv %0, a0"
                          : "=r"(r) : "r"(x) : "a0");
        lab_check(21, r, 1u + 4u + 9u + 16u);
        __asm__ volatile ("mv a0, %1\n mv a1, %2\n .insn 0x02B5050B\n mv %0, a0"
                          : "=r"(r) : "r"(x), "r"(y) : "a0", "a1");
        lab_check(22, r, 70u);
        uint32_t traps = ext_trap_record[4];
        __asm__ volatile (".insn r CUSTOM_0, 0, 1, x0, %0, %1" : : "r"(x), "r"(y));
        lab_check(23, ext_trap_record[4] - traps, 0u);
    }

    /* 4. Back-to-back dependence and mixing with MUL/DIV/loads (checks 24..26). */
    volatile uint32_t memory_word = 0x01010101u;
    int32_t r1 = xdot4(0x01020304u, memory_word);           /* 10 */
    int32_t r2 = xdot4((uint32_t)r1 * 0x01010101u, 0x01010101u);  /* 4 * 10 */
    lab_check(24, (uint32_t)r1, 10u);
    lab_check(25, (uint32_t)r2, 40u);
    lab_check(26, (uint32_t)(xdot4(0x02020202u, 0x03030303u) * 7 / 3), 56u); /* 24*7/3 */

    /* 5. Illegal neighbours: every word must trap with mcause 2 and mtval = word.
     *    Checks 30..56 (three per word). */
    EXT_EXPECT_ILLEGAL(30, 0x0000000B);   /* custom-0, funct7 = 0 */
    EXT_EXPECT_ILLEGAL(33, 0x0400000B);   /* custom-0, funct7 = 2 */
    EXT_EXPECT_ILLEGAL(36, 0xFE00000B);   /* custom-0, funct7 = 127 */
    EXT_EXPECT_ILLEGAL(39, 0x0200100B);   /* XDOT4 with funct3 = 1 */
    EXT_EXPECT_ILLEGAL(42, 0x0200700B);   /* XDOT4 with funct3 = 7 */
    EXT_EXPECT_ILLEGAL(45, 0x0200002B);   /* custom-1: no coprocessor in Lab 09 */
    EXT_EXPECT_ILLEGAL(48, 0x0000005B);   /* custom-2 */
    EXT_EXPECT_ILLEGAL(51, 0x0000007B);   /* custom-3 */
    EXT_EXPECT_ILLEGAL(54, 0x0600002B);   /* custom-1, funct7 = 3 */

    /* 6. The handler ran only for the nine illegal words (check 60). */
    lab_check(60, ext_trap_record[4], 9u);
    printf("xdot4 directed test: checksum=0x%08x traps=%u\n", checksum, ext_trap_record[4]);
    return 0;
}
