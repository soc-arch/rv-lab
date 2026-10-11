#include "lab.h"
#include "lab_perf.h"
#include <stdio.h>

static volatile uint32_t input[] = {
    1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16
};

__attribute__((noinline))
uint32_t measured_sum(const volatile uint32_t *values, unsigned count) {
    uint32_t sum = 0;
    for (unsigned i = 0; i < count; ++i) sum += values[i];
    return sum;
}

int main(void) {
    /* Build with CSR=1. The CSR and marker intervals have distinct boundaries. */
    lab_perf_begin();
    lab_roi_begin();
    uint32_t sum = measured_sum(input, 16);
    lab_roi_end();
    lab_perf_end();

    lab_check(501, sum, 136);
    lab_result(0, sum);
    printf("sum(1..16)=%u\n", sum);
    /* Read timing in the host report; keep functional output deterministic. */
    return 0;
}
