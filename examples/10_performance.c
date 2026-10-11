#include "lab.h"
#include "lab_perf.h"
#include <stdio.h>

/* Volatile loads prevent replacing the kernel with its known answer. */
static volatile uint32_t input[32] = {
    1, 2, 3, 4, 5, 6, 7, 8,
    9, 10, 11, 12, 13, 14, 15, 16,
    17, 18, 19, 20, 21, 22, 23, 24,
    25, 26, 27, 28, 29, 30, 31, 32
};

__attribute__((noinline))
static uint32_t measured_sum(const volatile uint32_t *values, unsigned count) {
    uint32_t sum = 0;
    for (unsigned i = 0; i < count; ++i) sum += values[i];
    return sum;
}

int main(void) {
    /* Two views of the same work: CSR snapshots surround the ROI markers.
     * Their boundaries differ, so their cycle/instruction totals also differ.
     * Keep preparation, checks, and output outside both intervals.
     */
    lab_perf_begin();
    lab_roi_begin();
    uint32_t sum = measured_sum(input, 32);
    lab_roi_end();
    lab_perf_end();

    lab_check(100, sum, 528);
    lab_result(0, sum);
    printf("sum(1..32)=%u\n", sum);
    /* The host reports CSR cycles, retired instructions, CPI, and optional
     * estimated time separately. Printing counters here would make the
     * functional console/signature differ between Spike and RTL.
     */
    return 0;
}
