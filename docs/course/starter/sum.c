#include "lab.h"
#include <stdio.h>

/* Volatile inputs keep the loop's loads visible in the cycle exercise. */
static volatile uint32_t input[] = {1, 2, 3, 4, 5, 6, 7, 8};

/* A named, non-inlined function gives the viewer a useful capture target. */
__attribute__((noinline))
uint32_t sum_values(const volatile uint32_t *values, unsigned count) {
    uint32_t sum = 0;
    for (unsigned i = 0; i < count; ++i) sum += values[i];
    return sum;
}

int main(void) {
    lab_roi_begin();
    uint32_t sum = sum_values(input, 8);
    lab_roi_end();

    lab_check(201, sum, 36);
    lab_result(0, sum);
    printf("sum=%u\n", sum);
    return 0;
}
