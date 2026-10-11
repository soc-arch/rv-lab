#ifndef CPU_LAB_CAMERA_KERNELS_H
#define CPU_LAB_CAMERA_KERNELS_H
#include <stdint.h>

/* The operation is selected at compile time so one run has one measured region. */
#define CAMERA_COPY 1
#define CAMERA_GRAY 2
#define CAMERA_SOBEL 3
#define CAMERA_PIPELINE 4

/* RGB888, row-major; RGB output contains width*height*3 bytes.
 * Gray storage contains width*height bytes. Buffers must not overlap.
 * Width and height must be at least 3 for the Sobel kernel. */
void camera_copy(const uint8_t *input, uint8_t *output, unsigned pixels);
void camera_grayscale(const uint8_t *input, uint8_t *gray,
                      uint8_t *output, unsigned pixels);
void camera_sobel(const uint8_t *gray, uint8_t *output,
                  unsigned width, unsigned height);
/* Interior convolution only: output must already have a zero boundary. */
void camera_sobel_pixels(const uint8_t *gray, uint8_t *output,
                         unsigned width, unsigned height);
void camera_pipeline(const uint8_t *input, uint8_t *gray, uint8_t *output,
                     unsigned width, unsigned height);
#endif
