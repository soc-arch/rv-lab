#include "lab.h"
#include <stdio.h>
static volatile uint32_t words[4] = {1, 2, 3, 4};
static volatile int8_t signed_byte = -7;
static volatile uint8_t unsigned_byte = 249;
static volatile int16_t signed_half = -300;
static volatile uint16_t unsigned_half = 65236;
int main(void) {
    uint32_t sum = 0;
    for (unsigned i = 0; i < 4; ++i) sum += words[i];
    lab_check(10, sum, 10);
    lab_check(11, (uint32_t)(int32_t)signed_byte, 0xfffffff9);
    lab_check(12, unsigned_byte, 249);
    lab_check(13, (uint32_t)(int32_t)signed_half, 0xfffffed4);
    lab_check(14, unsigned_half, 65236);
    unsigned_byte = 0xab; unsigned_half = 0xcdef; words[2] = 0x12345678;
    lab_check(15, unsigned_byte, 0xab);
    lab_check(16, unsigned_half, 0xcdef);
    lab_check(17, words[2], 0x12345678);
    lab_result(0, sum);
    puts("Byte, halfword and word accesses passed.");
    return 0;
}
