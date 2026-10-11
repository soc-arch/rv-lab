#include "lab.h"
#include "stdio.h"
#include <stdarg.h>
#include <stddef.h>

volatile uint32_t tohost[2] __attribute__((section(".htif"), aligned(64))) = {0, 0};
volatile uint32_t fromhost[2] __attribute__((section(".htif"), aligned(64))) = {0, 0};
volatile uint32_t lab_signature[LAB_SIGNATURE_WORDS]
    __attribute__((section(".signature"), aligned(16))) = {0};
volatile uint32_t lab_roi_begin_marker;
volatile uint32_t lab_roi_end_marker;

void lab_init(void) {
    for (unsigned i = 0; i < LAB_SIGNATURE_WORDS; ++i) lab_signature[i] = 0;
    lab_signature[0] = 0x4350554c;
    lab_signature[1] = 1;
}
void lab_check(uint32_t id, uint32_t actual, uint32_t expected) {
    unsigned n = lab_signature[2];
    if (n >= LAB_MAX_CHECKS) lab_finish(125);
    lab_signature[24 + 3*n] = id;
    lab_signature[25 + 3*n] = actual;
    lab_signature[26 + 3*n] = expected;
    lab_signature[2] = n + 1;
    if (actual != expected) lab_signature[3]++;
}
void lab_result(uint32_t index, uint32_t value) {
    if (index >= LAB_MAX_RESULTS) lab_finish(124);
    lab_signature[8 + index] = value;
    lab_signature[5] |= 1u << index;
}
void lab_roi_begin(void) {
    __asm__ volatile ("" ::: "memory");
    lab_roi_begin_marker = 1;
    __asm__ volatile ("" ::: "memory");
}
void lab_roi_end(void) {
    __asm__ volatile ("" ::: "memory");
    lab_roi_end_marker = 1;
    __asm__ volatile ("" ::: "memory");
}
void lab_finish(int status) {
    lab_signature[4] = status ? (uint32_t)status : (lab_signature[3] ? 1u : 0u);
    lab_signature[7] |= 0x80000000u; /* Application completed, even if it failed. */
    __asm__ volatile ("" ::: "memory");
    tohost[0] = lab_signature[4] ? 3u : 1u;
    for (;;) __asm__ volatile ("" ::: "memory");
}
int putchar(int c) {
    unsigned n = lab_signature[6];
    if (n < LAB_CONSOLE_BYTES) {
        ((volatile unsigned char *)&lab_signature[408])[n] = (unsigned char)c;
        lab_signature[6] = n + 1;
    } else lab_signature[7] |= 1u;
    return (unsigned char)c;
}
int puts(const char *s) { while (*s) putchar(*s++); putchar('\n'); return 0; }
static int number(uint32_t n, unsigned base, unsigned width, char pad) {
    char digits[32]; unsigned i = 0; int count = 0;
    do { unsigned d = n % base; n /= base; digits[i++] = "0123456789abcdef"[d]; } while (n);
    while (width > i) { putchar(pad); --width; ++count; }
    while (i) { putchar(digits[--i]); ++count; }
    return count;
}
int printf(const char *format, ...) {
    va_list ap; va_start(ap, format); int count = 0;
    while (*format) {
        if (*format++ != '%') { putchar(format[-1]); ++count; continue; }
        char pad = ' '; unsigned width = 0;
        if (*format == '0') { pad = '0'; ++format; }
        while (*format >= '0' && *format <= '9') { width = width*10 + (*format++ - '0'); }
        if (width > 64) width = 64;
        /* In ILP32, long and int are both 32 bits; fetch the matching va_arg type. */
        int is_long = (*format == 'l'); if (is_long) ++format;
        char spec = *format; if (!spec) break; ++format;
        if (spec == 's') {
            const char *s = va_arg(ap, const char *); if (!s) s = "(null)";
            while (*s) { putchar(*s++); ++count; }
        } else if (spec == 'c') { putchar(va_arg(ap, int)); ++count;
        } else if (spec == 'd' || spec == 'i') {
            int32_t v = is_long ? (int32_t)va_arg(ap, long) : va_arg(ap, int);
            uint32_t mag = (uint32_t)v;
            if (v < 0) {
                mag = 0u-mag;
                if (pad == ' ') {
                    unsigned digits = 1; uint32_t t = mag;
                    while (t >= 10) { t /= 10; ++digits; }
                    while (width > digits + 1) { putchar(' '); ++count; --width; }
                    width = 0;
                } else if (width) --width;
                putchar('-'); ++count;
            }
            count += number(mag, 10, width, pad);
        } else if (spec == 'u' || spec == 'x') {
            uint32_t v = is_long ? (uint32_t)va_arg(ap, unsigned long) : va_arg(ap, unsigned int);
            count += number(v, spec == 'x' ? 16 : 10, width, pad);
        } else if (spec == '%') { putchar('%'); ++count;
        } else { putchar('?'); ++count; }
    }
    va_end(ap); return count;
}
void *memcpy(void *dst, const void *src, size_t n) {
    unsigned char *d = dst; const unsigned char *s = src;
    while (n--) *d++ = *s++; return dst;
}
void *memset(void *dst, int value, size_t n) {
    unsigned char *d = dst; while (n--) *d++ = (unsigned char)value; return dst;
}
int memcmp(const void *a, const void *b, size_t n) {
    const unsigned char *x = a, *y = b;
    while (n--) { if (*x != *y) return (int)*x - (int)*y; ++x; ++y; } return 0;
}
