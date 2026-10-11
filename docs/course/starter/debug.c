#include "lab.h"
#include <stdio.h>

static volatile uint32_t input[] = {7, 2, 19, 4, 24, 3};

/* Contract: count is at least one. */
__attribute__((noinline))
uint32_t find_maximum(const volatile uint32_t *values, unsigned count) {
    uint32_t maximum = values[0];
    for (unsigned i = 1; i < count; ++i) {
        if (values[i] > maximum) maximum = values[i];
    }
    return maximum;
}

int main(void) {
    lab_roi_begin();
    uint32_t maximum = find_maximum(input, 6);
    lab_roi_end();

    /* Lab 03 intentionally begins with a wrong expected value. */
    lab_check(301, maximum, 99);
    lab_result(0, maximum);
    printf("maximum=%u\n", maximum);
    return 0;
}
