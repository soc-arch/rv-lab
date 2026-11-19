/* =============================================================================
 * HY-RV | ext_xacc
 * Description: Directed Lab 10 test: XACC state, wrap-around, register forms and side-effect-free rejects.
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
/* Run: make ext-test EXT=xacc RTL_DIR=$PWD/student/lab10/rtl */
#include "lab.h"
#include "stdio.h"
#include "xacc.h"
#include "ext_trap.h"

#ifndef HAVE_XACC
#error "Build this test with EXT=xacc"
#endif

static uint32_t lcg_state = 0x1234u;
static uint32_t lcg(void) { lcg_state = lcg_state * 1664525u + 1013904223u; return lcg_state; }

__attribute__((noinline)) static uint32_t busy_work(uint32_t x)
{
    /* MUL, DIV, loads and stores between coprocessor commands. */
    volatile uint32_t buffer[4] = {x, x * 3u, x / 7u, x % 5u};
    return buffer[0] + buffer[1] * buffer[2] - buffer[3];
}

int main(void)
{
    ext_trap_install();
    ext_irq_enable();

    /* 1. Reset value and clear (checks 1..2). */
    lab_check(1, (uint32_t)xacc_rd(), 0u);
    xacc_dot4(0x01010101u, 0x01010101u);
    xacc_clr();
    lab_check(2, (uint32_t)xacc_rd(), 0u);

    /* 2. Accumulation of hand-computed vectors (checks 3..6). */
    xacc_dot4(0x04030201u, 0x08070605u);                  /* +70 */
    lab_check(3, (uint32_t)xacc_rd(), 70u);
    xacc_dot4(0xFC03FE01u, 0x02FF0403u);                  /* -16 */
    lab_check(4, (uint32_t)xacc_rd(), 54u);
    lab_check(5, (uint32_t)xacc_rd(), 54u);               /* RD has no side effect */
    xacc_dot4(0x80808080u, 0x7F7F7F7Fu);                  /* -65024 */
    lab_check(6, (uint32_t)xacc_rd(), (uint32_t)(54 - 65024));

    /* 3. State survives other instructions and function calls (check 7). */
    uint32_t noise = busy_work(12345u);
    xacc_dot4(0x00000001u, 0x00000005u);                  /* +5 */
    noise += busy_work(noise);
    lab_check(7, (uint32_t)xacc_rd(), (uint32_t)(54 - 65024 + 5));
    lab_result(1, noise);

    /* 4. 32-bit wrap-around: 65537 * 65536 = 2^32 + 65536 (check 8). */
    xacc_clr();
    for (uint32_t i = 0; i < 65537u; ++i) xacc_dot4(0x80808080u, 0x80808080u);
    lab_check(8, (uint32_t)xacc_rd(), 65536u);

    /* 5. 400 pseudo-random commands against a software model (check 9). */
    xacc_clr();
    uint32_t model = 0;
    for (unsigned i = 0; i < 400; ++i) {
        uint32_t a = lcg(), b = lcg();
        xacc_dot4(a, b);
        model += (uint32_t)xdot4_ref(a, b);
    }
    lab_check(9, (uint32_t)xacc_rd(), model);
    lab_result(0, model);

    /* 6. Register forms (checks 10..12): RD into x0 is legal and harmless;
     *    DOT4 with rs1 == rs2; RD into a register that is also live. */
    uint32_t traps = ext_trap_record[4];
    __asm__ volatile (".insn r CUSTOM_1, 0, 2, x0, x0, x0");
    lab_check(10, ext_trap_record[4] - traps, 0u);
    xacc_clr();
    __asm__ volatile ("mv a5, %0\n .insn r CUSTOM_1, 0, 1, x0, a5, a5" : : "r"(0x02020202u) : "a5");
    lab_check(11, (uint32_t)xacc_rd(), 16u);
    int32_t before = xacc_rd();
    lab_check(12, (uint32_t)before, 16u);

    /* 7. Rejected words: illegal trap, mtval = word, and NO change to acc.
     *    acc = 16 now. Checks 20..52 (three per word). */
    EXT_EXPECT_ILLEGAL(20, 0x0600002B);   /* funct7 = 3: not an XACC command */
    EXT_EXPECT_ILLEGAL(23, 0xFE00002B);   /* funct7 = 127 */
    EXT_EXPECT_ILLEGAL(26, 0x0200102B);   /* DOT4 with funct3 = 1 */
    EXT_EXPECT_ILLEGAL(29, 0x020002AB);   /* DOT4 with rd = x5 (rd must be 0) */
    EXT_EXPECT_ILLEGAL(32, 0x0400802B);   /* RD with rs1 = x1 */
    EXT_EXPECT_ILLEGAL(35, 0x0410002B);   /* RD with rs2 = x1 */
    EXT_EXPECT_ILLEGAL(38, 0x000002AB);   /* CLR with rd = x5 */
    EXT_EXPECT_ILLEGAL(41, 0x0000802B);   /* CLR with rs1 = x1 */
    EXT_EXPECT_ILLEGAL(44, 0x0200000B);   /* XDOT4 word: custom-0 is not in Lab 10 */
    EXT_EXPECT_ILLEGAL(47, 0x0000005B);   /* custom-2 */
    EXT_EXPECT_ILLEGAL(50, 0x0000007B);   /* custom-3 */
    lab_check(53, (uint32_t)xacc_rd(), 16u);              /* rejects left acc alone */

    /* 8. The handler ran only for the eleven rejected words (check 60). */
    lab_check(60, ext_trap_record[4], 11u);
    printf("xacc directed test: model=0x%08x traps=%u\n", model, ext_trap_record[4]);
    return 0;
}
