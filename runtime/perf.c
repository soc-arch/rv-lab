#include "lab_perf.h"

volatile uint32_t lab_perf_record[LAB_PERF_RECORD_WORDS]
    __attribute__((section(".bss.lab_perf"), aligned(16)));

static inline uint64_t read_cycle(void) {
    uint32_t high, low, retry_high;
    do {
        __asm__ volatile (
            ".option push\n"
            ".option arch, +zicsr\n"
            "csrr %0, 0xb80\n"
            "csrr %1, 0xb00\n"
            "csrr %2, 0xb80\n"
            ".option pop\n"
            : "=&r" (high), "=&r" (low), "=&r" (retry_high)
            : : "memory");
    } while (high != retry_high);
    return ((uint64_t)high << 32) | low;
}

static inline uint64_t read_instret(void) {
    uint32_t high, low, retry_high;
    do {
        __asm__ volatile (
            ".option push\n"
            ".option arch, +zicsr\n"
            "csrr %0, 0xb82\n"
            "csrr %1, 0xb02\n"
            "csrr %2, 0xb82\n"
            ".option pop\n"
            : "=&r" (high), "=&r" (low), "=&r" (retry_high)
            : : "memory");
    } while (high != retry_high);
    return ((uint64_t)high << 32) | low;
}

uint64_t lab_perf_read_cycle(void) { return read_cycle(); }
uint64_t lab_perf_read_instret(void) { return read_instret(); }

static inline void store_counter(unsigned low_word, uint64_t value) {
    lab_perf_record[low_word] = (uint32_t)value;
    lab_perf_record[low_word + 1] = (uint32_t)(value >> 32);
}

static inline uint64_t load_counter(unsigned low_word) {
    uint32_t low = lab_perf_record[low_word];
    uint32_t high = lab_perf_record[low_word + 1];
    return ((uint64_t)high << 32) | low;
}

void lab_perf_begin(void) {
    __asm__ volatile ("" ::: "memory");
    lab_perf_record[LAB_PERF_FLAGS] = 0;
    lab_perf_record[LAB_PERF_MAGIC_WORD] = LAB_PERF_MAGIC;
    lab_perf_record[LAB_PERF_VERSION_WORD] = LAB_PERF_SCHEMA_VERSION;
    lab_perf_record[LAB_PERF_WORD_COUNT] = LAB_PERF_RECORD_WORDS;
    for (unsigned i = LAB_PERF_BEGIN_CYCLE_LO; i < LAB_PERF_RECORD_WORDS; ++i)
        lab_perf_record[i] = 0;

    uint64_t cycles = read_cycle();
    uint64_t instructions = read_instret();
    store_counter(LAB_PERF_BEGIN_CYCLE_LO, cycles);
    store_counter(LAB_PERF_BEGIN_INSTRET_LO, instructions);
    __asm__ volatile ("" ::: "memory");
    lab_perf_record[LAB_PERF_FLAGS] = LAB_PERF_FLAG_STARTED;
    __asm__ volatile ("" ::: "memory");
}

void lab_perf_end(void) {
    __asm__ volatile ("" ::: "memory");
    if (lab_perf_record[LAB_PERF_FLAGS] != LAB_PERF_FLAG_STARTED) return;

    uint64_t cycles = read_cycle();
    uint64_t instructions = read_instret();
    uint64_t begin_cycles = load_counter(LAB_PERF_BEGIN_CYCLE_LO);
    uint64_t begin_instructions = load_counter(LAB_PERF_BEGIN_INSTRET_LO);
    store_counter(LAB_PERF_END_CYCLE_LO, cycles);
    store_counter(LAB_PERF_END_INSTRET_LO, instructions);
    /* Unsigned subtraction is modulo 2^64, including a low-word rollover.
     * RV32 lowers these operations to pairs of 32-bit instructions; no 64-bit
     * division or compiler runtime library is required.
     */
    store_counter(LAB_PERF_DELTA_CYCLE_LO, cycles - begin_cycles);
    store_counter(LAB_PERF_DELTA_INSTRET_LO, instructions - begin_instructions);
    __asm__ volatile ("" ::: "memory");
    lab_perf_record[LAB_PERF_FLAGS] = LAB_PERF_FLAG_STARTED | LAB_PERF_FLAG_VALID;
    __asm__ volatile ("" ::: "memory");
}
