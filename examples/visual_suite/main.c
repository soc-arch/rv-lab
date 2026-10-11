/* One portable kernel invocation, one measured region, one complete RGB frame. */
#include "lab.h"
#include "image_kernels.h"
#include "render.h"
#include "visual_input.h"
#include <stdint.h>
#include <stddef.h>

#define PIXELS (VISUAL_WIDTH * VISUAL_HEIGHT)
#define RGB_BYTES (3u * PIXELS)
#define GUARD 16u
struct __attribute__((aligned(16))) guarded_output {
    volatile uint8_t before[GUARD];
    uint8_t pixels[RGB_BYTES];
    volatile uint8_t after[GUARD];
};
struct __attribute__((aligned(16))) guarded_scratch {
    volatile uint8_t before[GUARD];
    uint8_t pixels[6u * PIXELS];
    volatile uint8_t after[GUARD];
};
struct guarded_output visual_output_storage
    __attribute__((section(".signature_extra"), aligned(16))) = {0};
static struct guarded_scratch scratch;
_Static_assert(offsetof(struct guarded_output,pixels)==GUARD,"Host output offset");
_Static_assert(offsetof(struct guarded_output,after)==GUARD+RGB_BYTES,"Adjacent output guard");
_Static_assert(offsetof(struct guarded_scratch,after)==GUARD+6u*PIXELS,"Adjacent scratch guard");
_Static_assert(sizeof(visual_input)==RGB_BYTES,"Generated RGB input size");

static __attribute__((noinline)) uint32_t checksum(const volatile uint8_t *p,unsigned n)
{
    uint32_t hash=2166136261u;
    for(unsigned i=0;i<n;++i) hash=(hash^p[i])*16777619u;
    return hash;
}
static uint32_t guard_changes(const volatile uint8_t *p,uint8_t expected)
{
    uint32_t mask=0;
    for(unsigned i=0;i<GUARD;++i) if(p[i]!=expected) mask|=1u<<i;
    return mask;
}
int main(void)
{
    for(unsigned i=0;i<GUARD;++i) {
        visual_output_storage.before[i]=0xa5;visual_output_storage.after[i]=0x5a;
        scratch.before[i]=0x3c;scratch.after[i]=0xc3;
    }
    for(unsigned i=0;i<RGB_BYTES;++i) visual_output_storage.pixels[i]=0xcc;
    for(unsigned i=0;i<6u*PIXELS;++i) scratch.pixels[i]=0xee;
    const uint32_t before=checksum(visual_input,RGB_BYTES);
    lab_roi_begin();
#if VISUAL_OPERATION == 5
    const int status=render_frame(VISUAL_FRAME,VISUAL_WIDTH,VISUAL_HEIGHT,visual_output_storage.pixels);
#else
    const int status=image_run(VISUAL_OPERATION,visual_input,VISUAL_WIDTH,VISUAL_HEIGHT,
                               visual_output_storage.pixels,scratch.pixels);
#endif
    lab_roi_end();
    const uint32_t output_hash=checksum(visual_output_storage.pixels,RGB_BYTES);
    lab_check(300,(uint32_t)status,0);
    lab_check(301,guard_changes(visual_output_storage.before,0xa5),0);
    lab_check(302,guard_changes(visual_output_storage.after,0x5a),0);
    lab_check(303,guard_changes(scratch.before,0x3c),0);
    lab_check(304,guard_changes(scratch.after,0xc3),0);
    lab_check(305,checksum(visual_input,RGB_BYTES),before);
    lab_check(306,before,VISUAL_EXPECTED_INPUT_FNV);
    lab_check(307,output_hash,VISUAL_EXPECTED_OUTPUT_FNV);
    lab_result(0,VISUAL_OPERATION);lab_result(1,VISUAL_WIDTH);lab_result(2,VISUAL_HEIGHT);
    lab_result(3,RGB_BYTES);lab_result(4,output_hash);lab_result(5,before);lab_result(6,VISUAL_FRAME);
    return 0;
}
