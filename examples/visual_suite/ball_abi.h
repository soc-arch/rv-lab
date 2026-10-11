/* Teaching adapter: render.c consumes only these dimension bounds.
 * The original 4 MiB runtime/mailbox ABI is deliberately not part of this app. */
#ifndef HYRV_BALL_ABI_H
#define HYRV_BALL_ABI_H
#define BALL_MIN_WIDTH 64u
#define BALL_MIN_HEIGHT 48u
#define BALL_MAX_WIDTH 320u
#define BALL_MAX_HEIGHT 240u
#endif
