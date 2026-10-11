#ifndef HYRV_BALL_RENDER_H
#define HYRV_BALL_RENDER_H
#include <stdint.h>
/* Integer orthographic sphere, fixed animation timestep 1/60 s per frame.
 * Writes exactly width*height*3 RGB888 bytes, returns 0 or invalid-size -1.
 * No frame cache, floating point, allocator, or host-rendered image is used. */
int render_frame(uint32_t frame_index, unsigned width, unsigned height,
                 uint8_t *rgb);
uint32_t ball_isqrt(uint32_t value);
#endif
