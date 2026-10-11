"""Local snapshot of camera input and independent reference helpers.

Based on sw/camera_demo/run_demo.py; no CAS/DRISS dependency in this package.
Host reference pixels check the target; output PNGs always come from target RAM.
"""
import base64
import hashlib
from pathlib import Path
import struct
import zlib

MODES = {"copy": 1, "grayscale": 2, "sobel": 3, "pipeline": 4}

def fnv32(data):
    value = 2166136261
    for byte in data:
        value = ((value ^ byte) * 16777619) & 0xffffffff
    return value

def dimensions(width, height):
    if not (3 <= width <= 320 and 3 <= height <= 240):
        raise ValueError("Camera frames must be 3..320 pixels wide and 3..240 high for this 1 MiB SRAM lab")

def load_input(path=None, width=None, height=None):
    if (width is None) != (height is None):
        raise ValueError("Specify both --width and --height, or neither")
    if width is not None: dimensions(width, height)
    if path is None:
        width, height = width or 80, height or 60
        return width, height, sample_image(width, height), "HY-RV scene and edge chart"
    path = Path(path).expanduser().resolve()
    if path.suffix.lower() == ".ppm":
        w, h, rgb = read_ppm(path)
        if width is None or (w, h) == (width, height):
            dimensions(w, h)
            return w, h, rgb, path.name
    try:
        from PIL import Image
    except ImportError:
        raise ValueError("PNG/JPEG input or resizing requires Pillow; P6 PPM and the generated scene need no extra package")
    with Image.open(str(path)) as source:
        if width is None: dimensions(source.width, source.height)
        frame = source.convert("RGB")
        if width is not None: frame = frame.resize((width, height), Image.BILINEAR)
        dimensions(frame.width, frame.height)
        return frame.width, frame.height, frame.tobytes(), path.name

def prepare(args, directory):
    width, height, rgb, name = load_input(args.image, args.width, args.height)
    directory = Path(directory)
    (directory / "input.rgb").write_bytes(rgb)
    (directory / "input.png").write_bytes(png_bytes(width, height, rgb))
    (directory / "input.ppm").write_bytes(f"P6\n{width} {height}\n255\n".encode() + rgb)
    expected = reference_images(rgb, width, height)
    mode = args.camera_mode
    output = expected[{"copy": "passthrough", "grayscale": "grayscale", "sobel": "sobel", "pipeline": "sobel"}[mode]]
    rows = [", ".join(str(v) for v in rgb[i:i+24]) for i in range(0, len(rgb), 24)]
    header = f"/* Generated input, independently verified by the host. */\n#include <stdint.h>\n#define CAMERA_WIDTH {width}u\n#define CAMERA_HEIGHT {height}u\n#define CAMERA_EXPECTED_INPUT_FNV 0x{fnv32(rgb):08x}u\n#define CAMERA_EXPECTED_OUTPUT_FNV 0x{fnv32(output):08x}u\nstatic const uint8_t camera_input[{len(rgb)}] = {{\n" + ",\n".join(rows) + "\n};\n"
    (directory / "camera_input.h").write_text(header)
    return {"width": width, "height": height, "mode": mode, "operation": MODES[mode],
            "input_sha256": hashlib.sha256(rgb).hexdigest(), "input_name": name, "directory": directory}

def verify_output(words, manifest, directory, backend):
    camera = manifest["camera"]
    width, height = camera["width"], camera["height"]
    source = (directory / "input.rgb").read_bytes()
    if hashlib.sha256(source).hexdigest() != camera["input_sha256"]:
        raise ValueError("Input changed after compilation")
    reference = reference_images(source, width, height)
    expected = reference[{"copy": "passthrough", "grayscale": "grayscale", "sobel": "sobel", "pipeline": "sobel"}[camera["mode"]]]
    symbols = manifest["symbols"]
    offset = symbols["camera_output_storage"] + 16 - symbols["begin_signature"]
    raw = b"".join(struct.pack("<I", w) for w in words)
    length = width * height * 3
    if offset < 0 or offset + length > len(raw): raise ValueError("Camera output lies outside the signature dump")
    actual = raw[offset:offset+length]
    mismatch = sum(a != b for a, b in zip(actual, expected))
    (directory / f"{backend}.output.rgb").write_bytes(actual)
    (directory / f"{backend}.output.png").write_bytes(png_bytes(width, height, actual))
    return {"passed": mismatch == 0, "bytes_compared": length, "mismatched_bytes": mismatch,
            "output_sha256": hashlib.sha256(actual).hexdigest(),
            "expected_sha256": hashlib.sha256(expected).hexdigest(), "output_fnv32": fnv32(actual),
            "width": width, "height": height, "mode": camera["mode"]}

def frame_record(frame_id, title, png, width, height, roi_cycles=None, description=None):
    record = {"id": frame_id, "title": title, "width": width, "height": height,
              "data_url": "data:image/png;base64," + base64.b64encode(png).decode("ascii")}
    if roi_cycles is not None:
        record.update({"roi_cycles": roi_cycles, "pixels_processed": width * height})
    if description: record["description"] = description
    return record

def png_bytes(width, height, rgb):
    if len(rgb) != width * height * 3:
        raise ValueError('RGB byte count does not match dimensions')
    def chunk(kind, payload):
        return (struct.pack('>I', len(payload)) + kind + payload +
                struct.pack('>I', zlib.crc32(kind + payload) & 0xffffffff))
    rows = b''.join(b'\0' + rgb[y*width*3:(y+1)*width*3] for y in range(height))
    return (b'\x89PNG\r\n\x1a\n' +
            chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)) +
            chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b''))

def sample_image(width, height):
    """Deterministic scene + color/edge chart; no downloaded image required."""
    rgb = bytearray()
    for y in range(height):
        v = y * 240 // height
        for x in range(width):
            u = x * 320 // width
            color = (55 + v//3, 130 + v//3, 212 + v//8)
            if (u-257)**2 + (v-43)**2 < 22**2:
                color = (255, 221, 77)
            if v > 70+abs(u-74)*3//4:
                color = (63, 104, 127)
            if v > 95+abs(u-244)//2:
                color = (76, 133, 112)
            if v > 155:
                color = (102, 164, 70)
            if 91 < u < 207 and 110 < v < 187:
                color = (243, 206, 151)
            if 90 < v < 135 and abs(u-150) < (v-85)*3//2:
                color = (177, 66, 56)
            if 138 < u < 162 and 145 < v < 188:
                color = (77, 62, 56)
            if ((104 < u < 127) or (174 < u < 197)) and 142 < v < 166:
                color = (37, 82, 123) if u % 12 else (240, 240, 224)
            if 197 <= v < 216:
                bars = ((255,255,255),(255,255,0),(0,255,255),(0,255,0),
                        (255,0,255),(255,0,0),(0,0,255),(0,0,0))
                color = bars[min(7, u//40)]
            if v >= 218:
                if u < 160:
                    value = 255 if ((u//5 + v//5) % 2) else 0
                else:
                    value = (u-160)*255//159
                color = (value, value, value)
            rgb.extend(color)
    return bytes(rgb)

def read_ppm(path):
    data = Path(path).read_bytes()
    pos, tokens = 0, []
    while len(tokens) < 4:
        while pos < len(data) and data[pos] in b' \t\r\n':
            pos += 1
        if pos < len(data) and data[pos] == 35:
            end = data.find(b'\n', pos)
            if end < 0:
                raise ValueError('Unterminated PPM comment')
            pos = end + 1
            continue
        start = pos
        while pos < len(data) and data[pos] not in b' \t\r\n':
            pos += 1
        if pos == start:
            raise ValueError('Incomplete PPM header')
        tokens.append(data[start:pos])
    if tokens[0] != b'P6' or tokens[3] != b'255':
        raise ValueError('PPM input must be binary P6, maxval 255')
    if pos >= len(data):
        raise ValueError('Missing PPM pixel data')
    pos += 2 if data[pos:pos+2] == b'\r\n' else 1
    width, height = int(tokens[1]), int(tokens[2])
    rgb = data[pos:]
    if width <= 0 or height <= 0 or len(rgb) != width * height * 3:
        raise ValueError('PPM dimensions/pixel data length mismatch')
    return width, height, rgb

def reference_images(rgb, width, height):
    """Independent host oracle: explicit 2D convolution, never used as DUT output."""
    if len(rgb) != width * height * 3:
        raise ValueError('Reference input size mismatch')
    luminance = [(sum(a*b for a, b in zip(rgb[i:i+3], (77,150,29))) + 128)//256
                 for i in range(0, len(rgb), 3)]
    rows = [luminance[y*width:(y+1)*width] for y in range(height)]
    kx = ((-1,0,1),(-2,0,2),(-1,0,1))
    ky = ((-1,-2,-1),(0,0,0),(1,2,1))
    edges = bytearray(width * height * 3)
    for y in range(1, height-1):
        for x in range(1, width-1):
            gx = sum(rows[y+dy-1][x+dx-1]*kx[dy][dx]
                     for dy in range(3) for dx in range(3))
            gy = sum(rows[y+dy-1][x+dx-1]*ky[dy][dx]
                     for dy in range(3) for dx in range(3))
            value = min(255, abs(gx)+abs(gy))
            offset = (y*width+x)*3
            edges[offset:offset+3] = bytes((value,)*3)
    return {'passthrough': rgb,
            'grayscale': bytes(v for value in luminance for v in (value,)*3),
            'sobel': bytes(edges)}
