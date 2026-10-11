#ifndef CPU_LAB_H
#define CPU_LAB_H
#include <stdint.h>
#define LAB_SIGNATURE_WORDS 664u
#define LAB_MAX_CHECKS 128u
#define LAB_MAX_RESULTS 16u
#define LAB_CONSOLE_BYTES 1024u
void lab_check(uint32_t id, uint32_t actual, uint32_t expected);
void lab_result(uint32_t index, uint32_t value);
void lab_roi_begin(void);
void lab_roi_end(void);
void lab_init(void);
void lab_finish(int status) __attribute__((noreturn));
#endif
