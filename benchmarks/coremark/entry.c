/* Keep upstream initialization, iteration and CRC validation intact. */
#define main coremark_benchmark_main
#include "upstream/core_main.c"
#undef main

int main(void)
{
    coremark_benchmark_main();
    return coremark_check();
}
