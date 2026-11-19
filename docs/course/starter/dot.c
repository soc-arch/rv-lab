/* Lab 09/10 starter: an int8 dot product measured three ways from ONE source.
 *
 *   EXT=sw     xdot4() is portable C (shifts, sign-extension, four MULs)
 *   EXT=xdot4  xdot4() is one XDOT4 instruction in the core   (Lab 09)
 *   EXT=xacc   the coprocessor accumulates; no ADD in the loop (Lab 10)
 *
 * The input, the check and the measured region are identical in all builds.
 * Only dot_kernel() is inside the ROI. You do not need to edit this file.
 */
#include "lab.h"
#include "stdio.h"
#include "xdot4.h"
#include "xacc.h"

#define ELEMENTS 1024u              /* int8 elements per vector */
#define WORDS (ELEMENTS / 4u)       /* four int8 values per 32-bit word */

/* Word storage; bytes are reached through int8_t pointers (allowed aliasing). */
static uint32_t a_words[WORDS], b_words[WORDS];

#if defined(HAVE_XACC)
#define KERNEL "XACC coprocessor (custom-1)"
#elif defined(HAVE_XDOT4)
#define KERNEL "XDOT4 instruction (custom-0)"
#else
#define KERNEL "software xdot4_ref()"
#endif

/* Golden value: the obvious byte loop, outside the measured region. */
static int32_t dot_reference(const int8_t *x, const int8_t *y, unsigned n)
{
    int32_t sum = 0;
    for (unsigned i = 0; i < n; ++i) sum += (int32_t)x[i] * (int32_t)y[i];
    return sum;
}

/* The measured kernel: one call per 32-bit word pair. Both variants use the
 * same pointer loop, so they differ only in the work per word. */
__attribute__((noinline, noclone)) int32_t dot_kernel(const uint32_t *x, const uint32_t *y, unsigned words)
{
    const uint32_t *end = x + words;
#if defined(HAVE_XACC)
    xacc_clr();
    while (x != end) xacc_dot4(*x++, *y++);
    return xacc_rd();
#else
    int32_t sum = 0;
    while (x != end) sum += xdot4(*x++, *y++);
    return sum;
#endif
}

int main(void)
{
    int8_t *a = (int8_t *)a_words, *b = (int8_t *)b_words;
    uint32_t seed = 2026u;
    for (unsigned i = 0; i < ELEMENTS; ++i) {
        seed = seed * 1664525u + 1013904223u;
        a[i] = (int8_t)(seed >> 24);
        b[i] = (int8_t)(seed >> 16);
    }
    int32_t expected = dot_reference(a, b, ELEMENTS);

    lab_roi_begin();
    int32_t result = dot_kernel(a_words, b_words, WORDS);
    lab_roi_end();

    lab_check(1, (uint32_t)result, (uint32_t)expected);
    lab_result(0, (uint32_t)result);
    printf("kernel: %s\n", KERNEL);
    printf("dot product of %u int8 pairs = %d (expected %d)\n", ELEMENTS, result, expected);
    return 0;
}
