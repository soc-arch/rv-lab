#include "lab.h"
#include <stdio.h>
/* Volatile inputs keep the computation visible in the generated code. */
static volatile uint32_t input_a = 17, input_b = 5;
int main(void) {
    uint32_t a = input_a, b = input_b;
    lab_check(1, a + b, 22);
    lab_check(2, a - b, 12);
    lab_check(3, a ^ b, 20);
    lab_check(4, a << 2, 68);
    lab_result(0, a + b);
    printf("sum=%u, xor=0x%08x\n", a + b, a ^ b);
    return 0;
}
