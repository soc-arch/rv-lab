"""Portable visual applications: input preparation and independent pixel oracles.

Target output PNGs are decoded from the SRAM signature, never replaced by oracle
pixels. Pure Python references need no native compiler or parent repository.
"""
from __future__ import annotations
import hashlib
import math
from pathlib import Path
import struct
from camera_support import fnv32, load_input, png_bytes

APPS = {
    '07_denoise': {'mode': 'denoise', 'operation': 3, 'title': 'Impulse-noise removal', 'trace_symbol': 'image_run'},
    '08_cartoon': {'mode': 'cartoon', 'operation': 4, 'title': 'Integer cartoon filter', 'trace_symbol': 'image_run'},
    '09_ball': {'mode': 'ball', 'operation': 5, 'title': 'Integer bouncing ball', 'trace_symbol': 'render_frame'},
}

def dimensions(width, height, ball=False):
    minimum = (64,48) if ball else (3,3)
    if not isinstance(width,int) or not isinstance(height,int) or not minimum[0] <= width <= 160 or not minimum[1] <= height <= 120:
        raise ValueError(f'Visual frames must be {minimum[0]}..160 wide and {minimum[1]}..120 high in the interactive 1 MiB lab')

def add_impulse(rgb, width, height, seed=1):
    if len(rgb) != width*height*3: raise ValueError('RGB input byte count mismatch')
    if not isinstance(seed,int) or not 0 <= seed <= 0xffffffff: raise ValueError('Noise seed must be an unsigned 32-bit integer')
    result=bytearray(rgb)
    state=seed
    for p in range(width*height):
        state=(1664525*state+1013904223)&0xffffffff
        if state>>24 < 31:
            value=255 if state&(1<<23) else 0
            result[3*p:3*p+3]=bytes((value,)*3)
    return bytes(result)

def gray(rgb):
    return [(77*rgb[i]+150*rgb[i+1]+29*rgb[i+2]+128)//256 for i in range(0,len(rgb),3)]

def median(values,width,height,channels):
    # Complete sorted Python windows are independent of the target insertion sort.
    out=[]
    for y in range(height):
        for x in range(width):
            for channel in range(channels):
                out.append(sorted(values[(min(height-1,max(0,y+dy))*width+min(width-1,max(0,x+dx)))*channels+channel]
                                  for dy in (-1,0,1) for dx in (-1,0,1))[4])
    return out

def sobel(values,width,height):
    result=[0]*(width*height)
    kernels=((-1,0,1,-2,0,2,-1,0,1),(-1,-2,-1,0,0,0,1,2,1))
    for y in range(1,height-1):
        for x in range(1,width-1):
            window=[values[(y+dy)*width+x+dx] for dy in (-1,0,1) for dx in (-1,0,1)]
            gradients=[sum(a*b for a,b in zip(window,k)) for k in kernels]
            result[y*width+x]=min(255,sum(abs(v) for v in gradients))
    return result

def image_reference(mode,rgb,width,height):
    dimensions(width,height)
    if len(rgb)!=width*height*3: raise ValueError('RGB input byte count mismatch')
    if mode=='denoise': return bytes(v for v in median(gray(rgb),width,height,1) for _ in range(3))
    if mode=='cartoon':
        posterized=[32*(v//32)+16 for v in median(rgb,width,height,3)]
        edges=sobel(gray(posterized),width,height)
        return bytes(value//4 if edges[p//3]>=80 else value for p,value in enumerate(posterized))
    raise ValueError('Unknown image kernel')

def cdiv(numerator,denominator):
    """C signed division truncates toward zero, including negative normals."""
    magnitude=abs(numerator)//abs(denominator)
    return -magnitude if (numerator<0)!=(denominator<0) else magnitude

def ball_reference(frame,width,height):
    """Same documented scene geometry, independently evaluated in Python.

    Python math.isqrt validates the target's restoring integer square-root
    routine. This is an arithmetic oracle for the shared scene contract, not
    an independently designed rendering algorithm.
    """
    dimensions(width,height,ball=True)
    if not isinstance(frame,int) or not 0<=frame<=0xffffffff: raise ValueError('Frame index must be uint32')
    def triangle(value,period):
        p=value%period
        return min(p,period-p)
    scale=min(height,width*3//4)
    depth=triangle(frame%360,360)
    radius=scale//9+depth*scale//(180*22)
    margin=scale//5
    cx=margin+triangle((frame%420+70)%420,420)*(width-2*margin)//210
    phase=frame%96
    elevation=(height*3//8)*phase*(96-phase)//(48*48)
    contact=height*3//4+depth*height//(180*7)
    cy=contact-radius-elevation
    horizon=height*7//16
    out=bytearray(width*height*3)
    for y in range(height):
        for x in range(width):
            if y<horizon:
                grad=y*30//horizon
                color=(19+grad,29+grad,48+grad)
            else:
                denominator=y-horizon+height//12
                x_step=128*height//denominator
                z_cell=(height*64//denominator)//16
                fade=(y-horizon)*35//(height-horizon)
                world_x=(1<<20)-(width//2)*x_step+x*x_step
                light=107 if ((world_x>>12)+z_cell)&1 else 62
                color=(light+fade,light+fade+7,light+fade+14)
            p=(y*width+x)*3
            out[p:p+3]=bytes(color)
    sx=cx+elevation//6;sy=contact+radius//5
    rx=radius+elevation//3;ry=radius//3+elevation//12+1
    inv_rx2=65536//(rx*rx);inv_ry2=65536//(ry*ry)
    darkness=175-elevation*100//(height*3//8+1)
    for y in range(max(horizon,sy-ry),min(height,sy+ry+1)):
        for x in range(max(0,sx-rx),min(width,sx+rx+1)):
            distance=(x-sx)**2*inv_rx2+(y-sy)**2*inv_ry2
            if distance>=65536: continue
            edge=(65536-distance)>>8
            opacity=(edge*edge*darkness)>>16
            p=(y*width+x)*3
            out[p:p+3]=bytes((value*(256-opacity))>>8 for value in out[p:p+3])
    inv_radius=(16384+radius//2)//radius
    for y in range(max(0,cy-radius),min(height,cy+radius+1)):
        for x in range(max(0,cx-radius),min(width,cx+radius+1)):
            dx=x-cx;dy=y-cy
            z2=radius*radius-dx*dx-dy*dy
            if z2<0: continue
            z_q6=math.isqrt(z2<<12)
            nx=cdiv(dx*inv_radius,64);ny=cdiv(-dy*inv_radius,64);nz=z_q6*inv_radius//4096
            diffuse=max(0,min(255,cdiv(-100*nx+140*ny+190*nz,256)))
            specular=max(0,min(255,cdiv(-54*nx+76*ny+238*nz,256)))
            for _ in range(5):specular=(specular*specular)>>8
            light=48+((diffuse*190)>>8)
            rim=((256-nz)*(256-nz))>>10
            color=((28*light>>8)+specular+rim//3,(132*light>>8)+specular+rim//2,(242*light>>8)+specular+rim)
            p=(y*width+x)*3
            out[p:p+3]=bytes(max(0,min(255,v)) for v in color)
    return bytes(out)

def reference(meta,source):
    if meta['mode']=='ball':return ball_reference(meta['frame'],meta['width'],meta['height'])
    return image_reference(meta['mode'],source,meta['width'],meta['height'])

def prepare(args,directory):
    if args.app not in APPS:raise ValueError('Unknown visual application')
    directory=Path(directory)
    directory.mkdir(parents=True,exist_ok=True)
    meta=dict(APPS[args.app])
    width,height=getattr(args,'width',None),getattr(args,'height',None)
    if (width is None)!=(height is None):raise ValueError('Specify both width and height, or neither')
    # Modest defaults keep the complete frame practical in cycle-accurate RTL.
    width,height=64 if width is None else width,48 if height is None else height
    dimensions(width,height,ball=meta['mode']=='ball')
    frame=getattr(args,'frame',0)
    seed=getattr(args,'noise_seed',1)
    if not isinstance(frame,int) or not 0<=frame<=0xffffffff:raise ValueError('Frame index must be uint32')
    if not isinstance(seed,int) or not 0<=seed<=0xffffffff:raise ValueError('Noise seed must be uint32')
    if meta['mode']=='ball':
        rgb=bytes(width*height*3)
        name='Generated integer scene (no source image consumed)'
    else:
        width,height,clean,name=load_input(getattr(args,'image',None),width,height)
        (directory/'clean.rgb').write_bytes(clean)
        (directory/'clean.png').write_bytes(png_bytes(width,height,clean))
        rgb=add_impulse(clean,width,height,seed) if meta['mode']=='denoise' else clean
    meta.update(width=width,height=height,frame=frame,noise_seed=seed,input_name=name,
                input_sha256=hashlib.sha256(rgb).hexdigest())
    expected=reference(meta,rgb)
    meta['expected_output_sha256']=hashlib.sha256(expected).hexdigest()
    (directory/'input.rgb').write_bytes(rgb)
    (directory/'input.png').write_bytes(png_bytes(width,height,rgb))
    rows=[', '.join(str(v) for v in rgb[i:i+24]) for i in range(0,len(rgb),24)]
    header=f'''/* Generated RGB input and oracle hashes, not pre-rendered output. */
#include <stdint.h>
#define VISUAL_WIDTH {width}u
#define VISUAL_HEIGHT {height}u
#define VISUAL_OPERATION {meta['operation']}
#define VISUAL_FRAME {frame}u
#define VISUAL_EXPECTED_INPUT_FNV 0x{fnv32(rgb):08x}u
#define VISUAL_EXPECTED_OUTPUT_FNV 0x{fnv32(expected):08x}u
static const uint8_t visual_input[{len(rgb)}] = {{
'''+',\n'.join(rows)+'\n};\n'
    (directory/'visual_input.h').write_text(header)
    meta['directory']=directory
    return meta

def verify_output(words,manifest,directory,backend):
    meta=manifest['visual'];directory=Path(directory)
    source=(directory/'input.rgb').read_bytes()
    if hashlib.sha256(source).hexdigest()!=meta['input_sha256']:raise ValueError('Input changed after compilation')
    expected=reference(meta,source)
    symbols=manifest['symbols']
    offset=symbols['visual_output_storage']+16-symbols['begin_signature']
    raw=b''.join(struct.pack('<I',w) for w in words)
    length=meta['width']*meta['height']*3
    if offset<0 or offset+length>len(raw):raise ValueError('Visual output lies outside the signature dump')
    actual=raw[offset:offset+length]
    mismatch=sum(a!=b for a,b in zip(actual,expected))
    (directory/f'{backend}.output.rgb').write_bytes(actual)
    (directory/f'{backend}.output.png').write_bytes(png_bytes(meta['width'],meta['height'],actual))
    return {'passed':mismatch==0,'bytes_compared':length,'mismatched_bytes':mismatch,
            'output_sha256':hashlib.sha256(actual).hexdigest(),'expected_sha256':hashlib.sha256(expected).hexdigest(),
            'output_fnv32':fnv32(actual),'width':meta['width'],'height':meta['height'],
            'mode':meta['mode'],'frame':meta['frame'],
            'oracle':'Python scene geometry + math.isqrt' if meta['mode']=='ball' else 'Python sorted windows + convolution'}
