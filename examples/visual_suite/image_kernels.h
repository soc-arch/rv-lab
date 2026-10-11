#ifndef HYRV_IMAGE_KERNELS_H
#define HYRV_IMAGE_KERNELS_H
#include <stdint.h>

enum image_mode {
    IMAGE_GRAY = 1,
    IMAGE_SOBEL = 2,
    IMAGE_MEDIAN = 3,
    IMAGE_CARTOON = 4
};

/* Portable, allocation-free integer image kernels.
 *
 * Preconditions: RGB888 input and output each hold 3*width*height bytes;
 * scratch holds at least 6*width*height bytes. All three regions are disjoint.
 * Dimensions: 3..320 by 3..240. RGB channel order, row-major, top row first.
 * Returns 0 on success, -1 on invalid mode/size/null/overlapping regions.
 * Invalid arguments cause no output/scratch writes. Buffer capacities cannot
 * be inferred from pointers and remain the caller's responsibility.
 *
 * GRAY: (77*R + 150*G + 29*B + 128) >> 8, replicated to RGB.
 * SOBEL: gray above; min(255, abs(Gx)+abs(Gy)); one-pixel black border.
 * MEDIAN: gray above; median of a 3x3 window with coordinates clamped to the
 * image bounds (edge pixels repeat); result replicated to RGB.
 * CARTOON: separate 3x3 clamped-border median for each RGB channel, then
 * Q(v)=32*(v>>5)+16. Compute gray/Sobel from that quantized RGB. At pixels
 * with edge >= 80, divide every quantized channel by 4 (integer truncation).
 * Sobel's zero border leaves the quantized cartoon border uninked.
 * This is an educational median/posterize/ink pipeline, not bilateral filtering.
 * No floating point, libc calls, cached output images, or global state.
 */
int image_run(unsigned mode, const uint8_t *rgb, unsigned width, unsigned height,
              uint8_t *out, uint8_t *scratch);
#endif
