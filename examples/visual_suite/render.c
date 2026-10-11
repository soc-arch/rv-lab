#include "ball_abi.h"
#include "render.h"

/* Restoring square root: exact floor(sqrt(value)), all uint32 inputs. This is
 * deliberately a separate kernel suitable for a later custom instruction. */
uint32_t ball_isqrt(uint32_t value)
{
    uint32_t root = 0, bit = 1u << 30;
    while (bit > value) bit >>= 2;
    while (bit) {
        if (value >= root + bit) {
            value -= root + bit;
            root = (root >> 1) + bit;
        } else root >>= 1;
        bit >>= 2;
    }
    return root;
}

static int triangle(uint32_t frame, unsigned period)
{
    unsigned p = frame % period;
    return (int)(p <= period / 2 ? p : period - p);
}

static uint8_t clamp_byte(int v)
{
    return (uint8_t)(v < 0 ? 0 : v > 255 ? 255 : v);
}

int render_frame(uint32_t frame, unsigned width, unsigned height, uint8_t *rgb)
{
    if (!rgb || width < BALL_MIN_WIDTH || width > BALL_MAX_WIDTH ||
        height < BALL_MIN_HEIGHT || height > BALL_MAX_HEIGHT) return -1;
    const int w = (int)width, h = (int)height;
    const int scene_scale = h < w * 3 / 4 ? h : w * 3 / 4;
    /* The physical height follows a repeating ballistic arc. Horizontal
     * wall reflections are elastic; the bounce is prescribed, not a solver.
     * Modulo before adding phase avoids a UINT32_MAX frame-index overflow. */
    const int depth = triangle(frame % 360u, 360);
    const int radius = scene_scale / 9 + depth * scene_scale / (180 * 22);
    const int margin = scene_scale / 5;
    const int cx = margin + triangle((frame % 420u + 70u) % 420u, 420)
                           * (w - 2 * margin) / 210;
    const int phase = (int)(frame % 96u);
    const int elevation = (h * 3 / 8) * phase * (96 - phase) / (48 * 48);
    const int contact_y = h * 3 / 4 + depth * h / (180 * 7);
    const int cy = contact_y - radius - elevation;
    const int horizon = h * 7 / 16;

    /* Perspective floor: expensive division is per scanline, not per pixel.
     * World-grid coordinates stay nonnegative so shifts are portable. */
    for (int y = 0; y < h; ++y) {
        uint8_t *row = rgb + (unsigned)y * width * 3u;
        if (y < horizon) {
            const int grad = y * 30 / horizon;
            for (int x = 0; x < w; ++x) {
                row[3*x] = (uint8_t)(19 + grad);
                row[3*x+1] = (uint8_t)(29 + grad);
                row[3*x+2] = (uint8_t)(48 + grad);
            }
        } else {
            const int denominator = y - horizon + h / 12;
            const int x_step = 128 * h / denominator;
            const int z_cell = (h * 64 / denominator) / 16;
            const int fade = (y - horizon) * 35 / (h - horizon);
            int world_x = (1 << 20) - (w / 2) * x_step;
            for (int x = 0; x < w; ++x, world_x += x_step) {
                const int light = (((world_x >> 12) + z_cell) & 1) ? 107 : 62;
                row[3*x] = (uint8_t)(light + fade);
                row[3*x+1] = (uint8_t)(light + fade + 7);
                row[3*x+2] = (uint8_t)(light + fade + 14);
            }
        }
    }

    /* Elliptical soft contact shadow: height widens and weakens it. */
    const int sx = cx + elevation / 6, sy = contact_y + radius / 5;
    const int rx = radius + elevation / 3, ry = radius / 3 + elevation / 12 + 1;
    const int inv_rx2 = 65536 / (rx * rx), inv_ry2 = 65536 / (ry * ry);
    const int darkness = 175 - elevation * 100 / (h * 3 / 8 + 1);
    for (int y = sy - ry; y <= sy + ry; ++y) {
        if (y < horizon || y >= h) continue;
        const int dy = y - sy;
        for (int x = sx - rx; x <= sx + rx; ++x) {
            if (x < 0 || x >= w) continue;
            const int dx = x - sx;
            const int distance = dx * dx * inv_rx2 + dy * dy * inv_ry2;
            if (distance >= 65536) continue;
            const int edge = (65536 - distance) >> 8;
            const int opacity = (edge * edge * darkness) >> 16;
            uint8_t *p = rgb + ((unsigned)y * width + (unsigned)x) * 3u;
            p[0] = (uint8_t)((p[0] * (256 - opacity)) >> 8);
            p[1] = (uint8_t)((p[1] * (256 - opacity)) >> 8);
            p[2] = (uint8_t)((p[2] * (256 - opacity)) >> 8);
        }
    }

    const int inv_radius = (16384 + radius / 2) / radius;
    for (int y = cy - radius; y <= cy + radius; ++y) {
        if (y < 0 || y >= h) continue;
        const int dy = y - cy;
        for (int x = cx - radius; x <= cx + radius; ++x) {
            if (x < 0 || x >= w) continue;
            const int dx = x - cx;
            const int z2 = radius * radius - dx * dx - dy * dy;
            if (z2 < 0) continue;
            /* Reconstruct the visible sphere surface; normals use Q8. */
            const int z_q6 = (int)ball_isqrt((uint32_t)z2 << 12);
            const int nx = dx * inv_radius / 64;
            const int ny = -dy * inv_radius / 64;
            const int nz = z_q6 * inv_radius / 4096;
            int diffuse = (-100 * nx + 140 * ny + 190 * nz) / 256;
            if (diffuse < 0) diffuse = 0;
            if (diffuse > 255) diffuse = 255;
            int specular = (-54 * nx + 76 * ny + 238 * nz) / 256;
            if (specular < 0) specular = 0;
            if (specular > 255) specular = 255;
            /* Blinn-style highlight, power 32 through repeated Q8 squaring. */
            for (unsigned power = 0; power < 5; ++power)
                specular = (specular * specular) >> 8;
            const int light = 48 + (diffuse * 190 >> 8);
            const int rim = (256 - nz) * (256 - nz) >> 10;
            uint8_t *p = rgb + ((unsigned)y * width + (unsigned)x) * 3u;
            p[0] = clamp_byte((28 * light >> 8) + specular + rim / 3);
            p[1] = clamp_byte((132 * light >> 8) + specular + rim / 2);
            p[2] = clamp_byte((242 * light >> 8) + specular + rim);
        }
    }
    return 0;
}
