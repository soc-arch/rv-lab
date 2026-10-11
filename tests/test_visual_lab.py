"""Visual-kernel oracles, native arithmetic, and real same-ELF Spike/RTL checks.

Run: python3 tests/test_visual_lab.py -v
Set CPU_LAB_VISUAL_TEST_REPORT to retain a machine-readable firmware receipt.
"""
import argparse
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import random
import struct
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import lab
import visual_support as visual


def args(**override):
    values=dict(command='run',app='07_denoise',source=None,opt='O2',backend='both',rtl_dir=os.environ.get('LAB_RTL_DIR'),
                trace=False,trace_startup=False,trace_symbol=None,trace_limit=20000,wave=False,
                max_cycles=20000000,wall_seconds=120,iterations=1,validation=False,
                image=None,width=None,height=None,camera_mode='pipeline',frame=0,noise_seed=1,
                memory_profile='fast',port=8770)
    values.update(override)
    return argparse.Namespace(**values)


class NativeAndReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='cpu-visual-native-')
        cls.addClassCleanup(cls.temp.cleanup)
        base=ROOT/'examples/visual_suite'
        shared=Path(cls.temp.name)/'kernels.so'
        compiler=lab.native_c_compiler()
        lab.require([compiler,'-std=c11','-O2','-shared','-fPIC',base/'image_kernels.c',base/'render.c','-o',shared])
        cls.library=ctypes.CDLL(str(shared))
        bytep=ctypes.POINTER(ctypes.c_uint8)
        cls.library.image_run.argtypes=[ctypes.c_uint,bytep,ctypes.c_uint,ctypes.c_uint,bytep,bytep]
        cls.library.image_run.restype=ctypes.c_int
        cls.library.render_frame.argtypes=[ctypes.c_uint32,ctypes.c_uint,ctypes.c_uint,bytep]
        cls.library.render_frame.restype=ctypes.c_int
        cls.library.ball_isqrt.argtypes=[ctypes.c_uint32]
        cls.library.ball_isqrt.restype=ctypes.c_uint32

    def test_known_constant_and_impulse_median(self):
        clean=bytes((12,128,240))*35
        self.assertEqual(visual.image_reference('denoise',clean,7,5),bytes((106,)*105))
        self.assertEqual(visual.image_reference('cartoon',clean,7,5),bytes((16,144,240))*35)
        noisy=bytearray(bytes((90,90,90))*9);noisy[12:15]=bytes((255,)*3)
        self.assertEqual(visual.image_reference('denoise',noisy,3,3),bytes((90,)*27))

    def test_native_image_kernels_against_sorted_window_oracle(self):
        rng=random.Random(20261010)
        for width,height in ((3,3),(3,11),(11,3),(7,5)):
            rgb=bytes(rng.randrange(256) for _ in range(width*height*3))
            source=(ctypes.c_uint8*len(rgb)).from_buffer_copy(rgb)
            for mode,operation in [('denoise',3),('cartoon',4)]:
                output=(ctypes.c_uint8*len(rgb))()
                scratch=(ctypes.c_uint8*(width*height*6))()
                self.assertEqual(self.library.image_run(operation,source,width,height,output,scratch),0)
                self.assertEqual(bytes(output),visual.image_reference(mode,rgb,width,height))
                self.assertEqual(bytes(source),rgb)

    def test_integer_ball_extremes_and_square_root(self):
        samples=[0,1,2,3,4,15,16,17,0x7fffffff,0xffffffff]
        for value in (7,31,255,1024,65535):samples.extend((value*value-1,value*value,value*value+1))
        for value in samples:self.assertEqual(self.library.ball_isqrt(value),math.isqrt(value))
        for width,height in ((64,48),(65,49)):
            for frame in (0,1,23,48,95,96,359,419,0xffffffff):
                output=(ctypes.c_uint8*(width*height*3))()
                self.assertEqual(self.library.render_frame(frame,width,height,output),0)
                self.assertEqual(bytes(output),visual.ball_reference(frame,width,height),(frame,width,height))

    def test_reject_forged_pixels_and_changed_input(self):
        with tempfile.TemporaryDirectory(prefix='cpu-visual-forged-') as tmp:
            directory=Path(tmp)
            meta=visual.prepare(args(width=3,height=3),directory)
            manifest={'visual':{k:v for k,v in meta.items() if k!='directory'},
                      'symbols':{'begin_signature':0x80001000,'visual_output_storage':0x80001000}}
            expected=visual.reference(meta,(directory/'input.rgb').read_bytes())
            raw=bytearray(16)+bytearray(expected)+bytearray(1)
            self.assertTrue(visual.verify_output(list(struct.unpack('<11I',raw)),manifest,directory,'good')['passed'])
            raw[16+13]^=1
            result=visual.verify_output(list(struct.unpack('<11I',raw)),manifest,directory,'forged')
            self.assertFalse(result['passed']);self.assertEqual(result['mismatched_bytes'],1)
            self.assertEqual((directory/'forged.output.rgb').read_bytes(),raw[16:43])
            (directory/'input.rgb').write_bytes(bytes(27))
            with self.assertRaisesRegex(ValueError,'Input changed'):visual.verify_output(list(struct.unpack('<11I',raw)),manifest,directory,'changed')


class FirmwareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hardware=lab.build_hardware(args())
        cls.old_build=lab.BUILD
        cls.temp=tempfile.TemporaryDirectory(prefix='cpu-visual-firmware-')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.addClassCleanup(setattr,lab,'BUILD',cls.old_build)
        cls.directory=Path(cls.temp.name);lab.BUILD=cls.directory/'build'
        cls.evidence=[]

    @classmethod
    def tearDownClass(cls):
        path=os.environ.get('CPU_LAB_VISUAL_TEST_REPORT')
        if not path:
            fd,path=tempfile.mkstemp(prefix='cpu-visual-tests-',suffix='.json');os.close(fd)
        report=Path(path);report.parent.mkdir(parents=True,exist_ok=True)
        report.write_text(json.dumps({'schema_version':1,'rtl_build':cls.hardware[1],'cases':cls.evidence},indent=2)+'\n')
        print(f'Visual test evidence: {report}',flush=True)

    def execute(self,application,width,height,rgb=None,frame=0,stress=False,trace=False):
        image=None
        if rgb is not None:
            image=self.directory/f'{application}-{width}x{height}.ppm'
            image.write_bytes(f'P6\n{width} {height}\n255\n'.encode()+rgb)
        options=args(app=application,image=str(image) if image else None,width=width,height=height,
                     frame=frame,trace=trace,memory_profile='stress' if stress else 'fast')
        ok,out,summary=lab.run(options,self.hardware)
        self.assertTrue(ok,summary);self.assertTrue(summary['signature_match'])
        entry={'application':application,'width':width,'height':height,'frame':frame,'stress':stress,'backends':{}}
        actual={}
        for backend in ('sw','hw'):
            result=json.loads((out/f'{backend}.json').read_text())
            self.assertEqual(result['status'],'pass');self.assertEqual(result['check_count'],8)
            self.assertEqual(result['failure_count'],0)
            check=result['image_check']
            self.assertTrue(check['passed']);self.assertEqual(check['mismatched_bytes'],0)
            self.assertEqual(check['bytes_compared'],width*height*3)
            self.assertTrue((out/f'{backend}.output.png').read_bytes().startswith(b'\x89PNG'))
            actual[backend]=(out/f'{backend}.output.rgb').read_bytes()
            entry['backends'][backend]={'image_check':check}
            if backend=='hw':
                metrics=result['metrics'];self.assertEqual(metrics['roi_complete'],1)
                self.assertGreater(metrics['roi_cycles'],0);self.assertGreater(metrics['roi_retired'],0)
                entry['backends'][backend]['metrics']=metrics
        self.assertEqual(actual['sw'],actual['hw'])
        if trace:
            rows=[json.loads(line) for line in (out/'trace.jsonl').read_text().splitlines()]
            self.assertGreater(len(rows),0);self.assertLessEqual(len(rows),20000)
            self.assertTrue(all(row['schema_version']==2 for row in rows))
            self.assertTrue((out/'trace.html').is_file())
            entry['trace_rows']=len(rows)
        self.evidence.append(entry)

    def test_real_image_modes_small_odd_and_stalled(self):
        rng=random.Random(90210)
        cases=[('07_denoise',3,3,False),('07_denoise',3,11,True),('07_denoise',11,3,False),
               ('08_cartoon',3,3,False),('08_cartoon',7,5,True)]
        for application,width,height,stress in cases:
            rgb=bytes(rng.randrange(256) for _ in range(width*height*3))
            with self.subTest(application=application,width=width,height=height):
                self.execute(application,width,height,rgb,stress=stress,trace=width==7)

    def test_real_integer_ball_frames(self):
        self.execute('09_ball',64,48,frame=0,trace=True)
        self.execute('09_ball',65,49,frame=0xffffffff,stress=True)

if __name__=='__main__':unittest.main()
