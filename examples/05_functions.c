#include "lab.h"
#include <stdio.h>
static volatile int input[] = {3, -2, 7, 4};
static int uninitialized_global;
__attribute__((noinline)) static int square(int x) { return x*x; }
__attribute__((noinline)) static int energy(const volatile int *p, unsigned n) {
    int result = 0;
    for (unsigned i = 0; i < n; ++i) result += square(p[i]);
    return result;
}
int main(void) {
    lab_check(50, uninitialized_global, 0);
    int result = energy(input, 4);
    lab_check(51, result, 78);
    lab_result(0, result);
    printf("energy=%d\n", result);
    return 0;
}
