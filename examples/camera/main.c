/* One image, one operation, one ROI. The host generates camera_input.h. */
#include "lab.h"
#include "camera_kernels.h"
#include "camera_input.h"
#include <stddef.h>
#include <stdint.h>

#ifndef CAMERA_OPERATION
#define CAMERA_OPERATION CAMERA_PIPELINE
#endif
#if CAMERA_OPERATION < CAMERA_COPY || CAMERA_OPERATION > CAMERA_PIPELINE
#error "CAMERA_OPERATION must be COPY=1, GRAY=2, SOBEL=3 or PIPELINE=4"
#endif
#if CAMERA_WIDTH < 3 || CAMERA_WIDTH > 320 || CAMERA_HEIGHT < 3 || CAMERA_HEIGHT > 240
#error "The teaching image must be between 3x3 and 320x240"
#endif
#define CAMERA_PIXELS (CAMERA_WIDTH * CAMERA_HEIGHT)
#define CAMERA_RGB_BYTES (CAMERA_PIXELS * 3)
#define GUARD_BYTES 16

/* Byte guards are immediately adjacent even when the image byte count is odd.
 * Host extraction: ELF camera_output_storage address + 16, RGB_BYTES bytes.
 * The alignment can add trailing struct padding, never padding before pixels. */
struct __attribute__((aligned(16))) guarded_rgb {
    volatile uint8_t before[GUARD_BYTES];
    uint8_t pixels[CAMERA_RGB_BYTES];
    volatile uint8_t after[GUARD_BYTES];
};
struct __attribute__((aligned(16))) guarded_gray {
    volatile uint8_t before[GUARD_BYTES];
    uint8_t pixels[CAMERA_PIXELS];
    volatile uint8_t after[GUARD_BYTES];
};
struct guarded_rgb camera_output_storage
    __attribute__((section(".signature_extra"), aligned(16))) = {0};
struct guarded_gray camera_gray_storage;

_Static_assert(offsetof(struct guarded_rgb, pixels) == GUARD_BYTES,
               "The host extraction offset must remain 16");
_Static_assert(offsetof(struct guarded_rgb, after) == GUARD_BYTES + CAMERA_RGB_BYTES,
               "The output guard must directly follow the image");
_Static_assert(offsetof(struct guarded_gray, after) == GUARD_BYTES + CAMERA_PIXELS,
               "The gray guard must directly follow the image");
_Static_assert(sizeof(camera_input) == CAMERA_RGB_BYTES,
               "camera_input.h must contain exactly width*height*3 RGB888 bytes");

static __attribute__((noinline)) uint32_t fnv1a(const volatile uint8_t *data, unsigned count)
{
    uint32_t value = 2166136261u;
    for (unsigned i = 0; i < count; ++i)
        value = (value ^ data[i]) * 16777619u;
    return value;
}

static uint32_t changed_guard(const volatile uint8_t *guard, uint8_t expected)
{
    uint32_t mask = 0;
    for (unsigned i = 0; i < GUARD_BYTES; ++i)
        if (guard[i] != expected) mask |= 1u << i;
    return mask;
}

int main(void)
{
    uint8_t *const output = camera_output_storage.pixels;
    uint8_t *const gray = camera_gray_storage.pixels;
    /* Initialization, checksums and canary checks are outside the measured ROI. */
    for (unsigned i = 0; i < GUARD_BYTES; ++i) {
        camera_output_storage.before[i] = 0xa5;
        camera_output_storage.after[i] = 0x5a;
        camera_gray_storage.before[i] = 0x3c;
        camera_gray_storage.after[i] = 0xc3;
    }
    for (unsigned i = 0; i < CAMERA_RGB_BYTES; ++i) output[i] = 0xcc;
    for (unsigned i = 0; i < CAMERA_PIXELS; ++i) gray[i] = 0xcc;
    const uint32_t input_before = fnv1a(camera_input, CAMERA_RGB_BYTES);

#if CAMERA_OPERATION == CAMERA_SOBEL
    /* A Sobel-only experiment starts with an already prepared gray frame. */
    camera_grayscale(camera_input, gray, output, CAMERA_PIXELS);
#endif

    lab_roi_begin();
#if CAMERA_OPERATION == CAMERA_COPY
    camera_copy(camera_input, output, CAMERA_PIXELS);
#elif CAMERA_OPERATION == CAMERA_GRAY
    camera_grayscale(camera_input, gray, output, CAMERA_PIXELS);
#elif CAMERA_OPERATION == CAMERA_SOBEL
    camera_sobel(gray, output, CAMERA_WIDTH, CAMERA_HEIGHT);
#else
    camera_pipeline(camera_input, gray, output, CAMERA_WIDTH, CAMERA_HEIGHT);
#endif
    lab_roi_end();

    const uint32_t input_after = fnv1a(camera_input, CAMERA_RGB_BYTES);
    const uint32_t output_hash = fnv1a(output, CAMERA_RGB_BYTES);
    lab_check(200, changed_guard(camera_output_storage.before, 0xa5), 0);
    lab_check(201, changed_guard(camera_output_storage.after, 0x5a), 0);
    lab_check(202, changed_guard(camera_gray_storage.before, 0x3c), 0);
    lab_check(203, changed_guard(camera_gray_storage.after, 0xc3), 0);
    lab_check(204, input_after, input_before);
#ifdef CAMERA_EXPECTED_INPUT_FNV
    lab_check(205, input_after, CAMERA_EXPECTED_INPUT_FNV);
#endif
#ifdef CAMERA_EXPECTED_OUTPUT_FNV
    lab_check(206, output_hash, CAMERA_EXPECTED_OUTPUT_FNV);
#endif
    lab_result(0, CAMERA_OPERATION);
    lab_result(1, CAMERA_WIDTH);
    lab_result(2, CAMERA_HEIGHT);
    lab_result(3, CAMERA_RGB_BYTES);
    lab_result(4, output_hash);
    lab_result(5, input_after);
#if CAMERA_OPERATION == CAMERA_COPY
    lab_result(6, 0); /* This operation does not consume/produce a gray frame. */
#else
    lab_result(6, fnv1a(gray, CAMERA_PIXELS));
#endif
    /* Runtime derives failure from lab_check records even when main returns 0.
     * The host additionally compares EVERY output byte with its Python oracle. */
    return 0;
}
