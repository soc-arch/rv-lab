/* Arithmetic adapted from sw/camera_demo/main.c in the HY-RV repository.
 * This snapshot retains its exact RGB rounding, Sobel signs, black boundary and
 * L1 saturation. Only function boundaries and buffer parameters were added.
 * No camera controller, MMIO, accelerator or custom instruction is involved. */
#include "camera_kernels.h"

#define NOINLINE __attribute__((noinline))

static unsigned magnitude(int value)
{
    return value < 0 ? (unsigned)-value : (unsigned)value;
}

NOINLINE void camera_copy(const uint8_t *input, uint8_t *output, unsigned pixels)
{
    for (unsigned i = 0; i < pixels * 3; ++i)
        output[i] = input[i];
}

NOINLINE void camera_grayscale(const uint8_t *input, uint8_t *gray,
                               uint8_t *output, unsigned pixels)
{
    for (unsigned i = 0; i < pixels; ++i) {
        /* Integer luminance approximation; coefficients sum to 256.
         * It is not a linear-light color conversion or a Bayer RAW decoder. */
        unsigned y = (77u * input[3*i] + 150u * input[3*i+1] +
                      29u * input[3*i+2] + 128u) >> 8;
        gray[i] = (uint8_t)y;
        output[3*i] = output[3*i+1] = output[3*i+2] = (uint8_t)y;
    }
}

NOINLINE void camera_sobel(const uint8_t *gray, uint8_t *output,
                           unsigned width, unsigned height)
{
    const unsigned pixels = width * height;
    /* Define every output byte, including the one-pixel black boundary. */
    for (unsigned i = 0; i < pixels * 3; ++i)
        output[i] = 0;
    camera_sobel_pixels(gray, output, width, height);
}

/* Separate symbol lets the viewer begin at useful stencil arithmetic rather
 * than spending its capture budget on the full output-clear loop. */
NOINLINE void camera_sobel_pixels(const uint8_t *gray, uint8_t *output,
                                  unsigned width, unsigned height)
{
    for (unsigned y = 1; y + 1 < height; ++y) {
        for (unsigned x = 1; x + 1 < width; ++x) {
            unsigned p = y * width + x;
            int a = gray[p-width-1], b = gray[p-width], c = gray[p-width+1];
            int d = gray[p-1], f = gray[p+1];
            int g = gray[p+width-1], h = gray[p+width], i = gray[p+width+1];
            int gx = -a + c - 2*d + 2*f - g + i;
            int gy = -a - 2*b - c + g + 2*h + i;
            unsigned edge = magnitude(gx) + magnitude(gy);
            if (edge > 255) edge = 255;
            output[3*p] = output[3*p+1] = output[3*p+2] = (uint8_t)edge;
        }
    }
}

NOINLINE void camera_pipeline(const uint8_t *input, uint8_t *gray,
                              uint8_t *output, unsigned width, unsigned height)
{
    camera_grayscale(input, gray, output, width * height);
    camera_sobel(gray, output, width, height);
}
