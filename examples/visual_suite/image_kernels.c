#include "image_kernels.h"

static int overlap(const uint8_t *a, unsigned a_bytes,
                   const uint8_t *b, unsigned b_bytes)
{
    const uintptr_t aa = (uintptr_t)a, bb = (uintptr_t)b;
    /* Subtraction avoids overflowing an end-address calculation. */
    return aa <= bb ? bb - aa < a_bytes : aa - bb < b_bytes;
}

static uint8_t gray(const uint8_t *rgb)
{
    return (uint8_t)((77u * rgb[0] + 150u * rgb[1] + 29u * rgb[2] + 128u) >> 8);
}

static unsigned magnitude(int value)
{
    return value < 0 ? (unsigned)-value : (unsigned)value;
}

static uint8_t sobel_at(const uint8_t *g, unsigned width, unsigned p)
{
    const int a = g[p-width-1], b = g[p-width], c = g[p-width+1];
    const int d = g[p-1], f = g[p+1];
    const int h0 = g[p+width-1], h1 = g[p+width], h2 = g[p+width+1];
    const int gx = -a + c - 2*d + 2*f - h0 + h2;
    const int gy = -a - 2*b - c + h0 + 2*h1 + h2;
    const unsigned edge = magnitude(gx) + magnitude(gy);
    return (uint8_t)(edge > 255 ? 255 : edge);
}

static unsigned clamp_coord(int coordinate, unsigned limit)
{
    if (coordinate < 0) return 0;
    if ((unsigned)coordinate >= limit) return limit - 1;
    return (unsigned)coordinate;
}

static uint8_t median9(uint8_t v[9])
{
    /* Explicit insertion sort is the scalar baseline. A later selection
     * network/custom comparison experiment must preserve this exact median. */
    for (unsigned i = 1; i < 9; ++i) {
        const uint8_t value = v[i];
        unsigned j = i;
        while (j && v[j-1] > value) {
            v[j] = v[j-1];
            --j;
        }
        v[j] = value;
    }
    return v[4];
}

static uint8_t median_at(const uint8_t *input, unsigned width, unsigned height,
                         unsigned x, unsigned y, unsigned channels, unsigned channel)
{
    uint8_t values[9];
    unsigned i = 0;
    for (int dy = -1; dy <= 1; ++dy) {
        const unsigned row = clamp_coord((int)y + dy, height) * width;
        for (int dx = -1; dx <= 1; ++dx) {
            const unsigned p = row + clamp_coord((int)x + dx, width);
            values[i++] = input[p * channels + channel];
        }
    }
    return median9(values);
}

int image_run(unsigned mode, const uint8_t *rgb, unsigned width, unsigned height,
              uint8_t *out, uint8_t *scratch)
{
    if (mode < IMAGE_GRAY || mode > IMAGE_CARTOON || !rgb || !out || !scratch ||
        width < 3 || width > 320 || height < 3 || height > 240) return -1;
    const unsigned pixels = width * height, bytes = pixels * 3;
    if (overlap(rgb, bytes, out, bytes) || overlap(rgb, bytes, scratch, pixels * 6) ||
        overlap(out, bytes, scratch, pixels * 6)) return -1;

    if (mode == IMAGE_GRAY) {
        for (unsigned p = 0; p < pixels; ++p) {
            const uint8_t value = gray(rgb + 3*p);
            out[3*p] = out[3*p+1] = out[3*p+2] = value;
        }
        return 0;
    }

    if (mode == IMAGE_CARTOON) {
        for (unsigned y = 0; y < height; ++y)
            for (unsigned x = 0; x < width; ++x) {
                const unsigned p = y * width + x;
                for (unsigned c = 0; c < 3; ++c) {
                    const uint8_t value = median_at(rgb, width, height, x, y, 3, c);
                    out[3*p+c] = (uint8_t)(((unsigned)value >> 5) * 32 + 16);
                }
                scratch[p] = gray(out + 3*p);
            }
        /* Read only the completed gray scratch while applying ink in-place. */
        for (unsigned y = 1; y + 1 < height; ++y)
            for (unsigned x = 1; x + 1 < width; ++x) {
                const unsigned p = y * width + x;
                if (sobel_at(scratch, width, p) >= 80) {
                    out[3*p] /= 4;
                    out[3*p+1] /= 4;
                    out[3*p+2] /= 4;
                }
            }
        return 0;
    }

    for (unsigned p = 0; p < pixels; ++p) scratch[p] = gray(rgb + 3*p);
    if (mode == IMAGE_MEDIAN) {
        for (unsigned y = 0; y < height; ++y)
            for (unsigned x = 0; x < width; ++x) {
                const uint8_t value = median_at(scratch, width, height, x, y, 1, 0);
                const unsigned p = y * width + x;
                out[3*p] = out[3*p+1] = out[3*p+2] = value;
            }
    } else {
        for (unsigned p = 0; p < bytes; ++p) out[p] = 0;
        for (unsigned y = 1; y + 1 < height; ++y)
            for (unsigned x = 1; x + 1 < width; ++x) {
                const unsigned p = y * width + x;
                const uint8_t value = sobel_at(scratch, width, p);
                out[3*p] = out[3*p+1] = out[3*p+2] = value;
            }
    }
    return 0;
}
