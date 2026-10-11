#include "lab.h"
#include <stdio.h>
#define OP(name, a, b) ({ uint32_t out; __asm__ volatile(name " %0,%1,%2" : "=r"(out) : "r"((uint32_t)(a)), "r"((uint32_t)(b))); out; })
int main(void) {
    lab_check(30, OP("mul", 17, 5), 85);
    lab_check(31, OP("mulh", -2, 3), 0xffffffff);
    lab_check(32, OP("mulhsu", -2, 0xffffffff), 0xfffffffe);
    lab_check(33, OP("mulhu", 0xffffffff, 0xffffffff), 0xfffffffe);
    lab_check(34, OP("div", -17, 5), (uint32_t)-3);
    lab_check(35, OP("divu", 17, 5), 3);
    lab_check(36, OP("rem", -17, 5), (uint32_t)-2);
    lab_check(37, OP("remu", 17, 5), 2);
    /* Assembly exercises defined ISA corner cases without C undefined behavior. */
    lab_check(38, OP("div", 17, 0), 0xffffffff);
    lab_check(39, OP("divu", 17, 0), 0xffffffff);
    lab_check(40, OP("rem", 17, 0), 17);
    lab_check(41, OP("remu", 17, 0), 17);
    lab_check(42, OP("div", 0x80000000, -1), 0x80000000);
    lab_check(43, OP("rem", 0x80000000, -1), 0);
    puts("All eight M instructions and division corner cases passed.");
    return 0;
}
