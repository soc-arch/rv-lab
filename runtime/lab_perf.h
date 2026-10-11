#ifndef CPU_LAB_PERF_H
#define CPU_LAB_PERF_H

#include <stdint.h>

/* Optional M-mode counters: requires Zicsr and the mcycle/minstret CSRs.
 * Keep counter values out of printf(), lab_result(), and lab_check(): Spike's
 * functional counters are not RTL timing, and those APIs form the functional
 * signature compared between the two backends.
 */
#define LAB_PERF_MAGIC 0x4c504d31u
#define LAB_PERF_SCHEMA_VERSION 1u
#define LAB_PERF_RECORD_WORDS 16u
#define LAB_PERF_FLAG_STARTED 1u
#define LAB_PERF_FLAG_VALID 2u

/* Each 64-bit value is stored as its low word followed by its high word.
 * The host may report the record only when STARTED and VALID are both set.
 */
enum lab_perf_record_word {
    LAB_PERF_MAGIC_WORD = 0,
    LAB_PERF_VERSION_WORD = 1,
    LAB_PERF_WORD_COUNT = 2,
    LAB_PERF_FLAGS = 3,
    LAB_PERF_BEGIN_CYCLE_LO = 4,
    LAB_PERF_BEGIN_CYCLE_HI = 5,
    LAB_PERF_BEGIN_INSTRET_LO = 6,
    LAB_PERF_BEGIN_INSTRET_HI = 7,
    LAB_PERF_END_CYCLE_LO = 8,
    LAB_PERF_END_CYCLE_HI = 9,
    LAB_PERF_END_INSTRET_LO = 10,
    LAB_PERF_END_INSTRET_HI = 11,
    LAB_PERF_DELTA_CYCLE_LO = 12,
    LAB_PERF_DELTA_CYCLE_HI = 13,
    LAB_PERF_DELTA_INSTRET_LO = 14,
    LAB_PERF_DELTA_INSTRET_HI = 15
};

/* Ordinary zero-initialized SRAM, deliberately outside begin/end_signature. */
extern volatile uint32_t lab_perf_record[LAB_PERF_RECORD_WORDS];

/* RV32 high-low-high reads retry if the low word rolls over while reading.
 * They do not write, clear, or inhibit the counters. The returned values are
 * cycles/instructions, not seconds or host wall-clock time.
 */
uint64_t lab_perf_read_cycle(void);
uint64_t lab_perf_read_instret(void);

/* One region per completed run; another begin replaces the previous record.
 * Each snapshot reads cycle and then instret, so the pair is not atomic.
 * The deltas include read/call/recording overhead between the two snapshots.
 * No implicit printing occurs. The host prints the separate performance record.
 * end without a fresh begin leaves the record unchanged.
 */
void lab_perf_begin(void);
void lab_perf_end(void);

#endif
