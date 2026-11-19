/* =============================================================================
 * HY-RV | ext_trap.h
 * Description: Minimal M-mode trap recorder for the Lab 09/10 illegal-encoding tests.
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
#ifndef HYRV_EXT_TRAP_H
#define HYRV_EXT_TRAP_H

#include <stdint.h>
#include "lab.h"

/* Exceptions: the handler records mcause/mtval/mepc, counts the trap, skips the
 * 4-byte faulting instruction and returns. Interrupts (mcause bit 31) only
 * increment their own counter and return to the interrupted instruction, so
 * they never disturb the exception record. Spike and the RTL both run it, so
 * their complete signatures can still be compared. Only t0/t1 are used.
 * Words: [0] saved t1, [1] mcause, [2] mtval, [3] mepc, [4] exception count,
 *        [5] interrupt count (RTL with +irq_period only; never in the signature). */
volatile uint32_t ext_trap_record[6];

__attribute__((naked, aligned(4))) void ext_trap_handler(void)
{
    __asm__ volatile (
        ".option push\n"
        ".option arch, +zicsr\n"
        "csrw mscratch, t0\n"
        "la   t0, ext_trap_record\n"
        "sw   t1, 0(t0)\n"
        "csrr t1, mcause\n"
        "bltz t1, 1f\n"                          /* interrupt: count only */
        "sw   t1, 4(t0)\n"
        "csrr t1, mtval\n   sw t1, 8(t0)\n"
        "csrr t1, mepc\n    sw t1, 12(t0)\n"
        "lw   t1, 16(t0)\n  addi t1, t1, 1\n  sw t1, 16(t0)\n"
        "csrr t1, mepc\n    addi t1, t1, 4\n  csrw mepc, t1\n"
        "lw   t1, 0(t0)\n"
        "csrr t0, mscratch\n"
        "mret\n"
        "1: lw t1, 20(t0)\n  addi t1, t1, 1\n  sw t1, 20(t0)\n"
        "lw   t1, 0(t0)\n"
        "csrr t0, mscratch\n"
        "mret\n"
        ".option pop\n");
}

static inline void ext_trap_install(void)
{
    __asm__ volatile (".option push\n.option arch, +zicsr\ncsrw mtvec, %0\n.option pop"
                      : : "r"(ext_trap_handler) : "memory");
}

/* Enable machine software interrupts (mie.MSIE, mstatus.MIE). Spike never raises
 * MSIP here; the RTL testbench does only with +irq_period. Results must not depend
 * on whether or where interrupts arrive. */
static inline void ext_irq_enable(void)
{
    __asm__ volatile (".option push\n.option arch, +zicsr\n"
                      "csrs mie, %0\n csrs mstatus, %1\n.option pop"
                      : : "r"(1u << 3), "r"(1u << 3) : "memory");
}

/* Execute one raw 32-bit word and check that it raised exactly one
 * illegal-instruction exception (mcause 2) with mtval equal to the word.
 * Uses three check slots: base, base+1, base+2. */
#define EXT_EXPECT_ILLEGAL(base, word) do {                                   \
        uint32_t before_ = ext_trap_record[4];                                \
        __asm__ volatile (".insn " #word ::: "memory");                       \
        lab_check((base), ext_trap_record[4] - before_, 1u);                  \
        lab_check((base) + 1, ext_trap_record[1], 2u);                        \
        lab_check((base) + 2, ext_trap_record[2], (uint32_t)(word));          \
    } while (0)

#endif
