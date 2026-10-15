#!/usr/bin/env python3
# =============================================================================
# HY-RV | memory_protocol
# Description: Independent memory and CPU public-port protocol regression.
#
# Purpose: Computer architecture and RTL design education and lab exercises.
# Maintained by: DSAL (Digital System Architecture Lab), Hanyang University
# Website: https://dsa.hanyang.ac.kr
# Supervisor: Prof. Ji-Hoon Kim (jhoonkim@hanyang.ac.kr)
#
# AI tools such as Codex or Claude may have assisted in creating or modifying
# this file. See the applicable manifests and verification records for
# file-specific provenance, revision history, and validation evidence.
# Preserve existing license, copyright, and original author notices.
# =============================================================================

"""Memory-v1 boundary tests: independent RAM driver and public-port CPU tests.

Run with the same prerequisites as lab.py. No CPU hierarchy or DPI is used.
The report retains exact source/build identities, commands and observed coverage.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import lab
import core_config

BASE = 0x80000000

def digest_files(files):
    return {str(p): lab.digest(p) for p in files}

def build_standalone(rtl, out, config):
    adapter = core_config.adapter_path(config['memory_adapter'])
    files = [rtl / 'common/mem_if.sv', adapter, ROOT / 'tests/memory_protocol_tb.sv']
    cxx = lab.cxx_compiler()
    identity = {'files': digest_files(files), 'memory_adapter': {'name': config['memory_adapter'], 'source': lab.source_label(adapter), 'sha256': lab.digest(adapter)},
                'verilator': lab.version(lab.tool('verilator')),
                'verilator_path': lab.tool('verilator'), 'cxx_path': cxx, 'cxx': lab.version(cxx), 'flags': '--binary --timing --assert'}
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    dest = out / 'ram-build' / key
    binary = dest / 'Vmemory_protocol_tb'
    if not binary.exists():
        dest.mkdir(parents=True, exist_ok=True)
        build_env = os.environ.copy()
        for name in ('MAKEFLAGS', 'MFLAGS', 'MAKEOVERRIDES', 'OPT'):
            build_env.pop(name, None)
        build_env.setdefault('CCACHE_DIR', str(lab.BUILD / 'ccache'))
        lab.require([lab.tool('verilator'), '--binary', '--timing', '--assert', '--top-module', 'memory_protocol_tb',
                     '--Mdir', dest, '-j', '4', '-MAKEFLAGS', f'CXX={cxx}', *files], dest / 'build.log', timeout=600, env=build_env)
    return binary, identity

def compile_program(out, body):
    out.mkdir(parents=True, exist_ok=True)
    source = out / 'program.S'
    source.write_text('.option norvc\n.option norelax\n.section .text\n.globl _start\n_start:\n' + body + '''
finish:
    la t0, tohost
    li t1, 1
    sw t1, 0(t0)
stop: j stop
.org 0x200
scratch: .word 0x12345678
         .word 0x87654321
.org 0x300
.balign 8
tohost: .dword 0
''')
    elf = out / 'program.elf'
    lab.require([lab.tool('riscv32-unknown-elf-gcc'), '-march=rv32im', '-mabi=ilp32', '-nostdlib', '-nostartfiles',
                 '-mno-relax', '-Wl,--no-relax', '-Wl,-Ttext=0x80000000', source, '-o', elf], out / 'compile.log')
    symbols = {}
    for line in lab.require([lab.tool('riscv32-unknown-elf-nm'), '-n', elf]).splitlines():
        parts = line.split()
        if len(parts) == 3:
            try: symbols[parts[2]] = int(parts[0], 16)
            except ValueError: pass
    binary = out / 'program.bin'
    lab.require([lab.tool('riscv32-unknown-elf-objcopy'), '-O', 'binary', '-j', '.text', elf, binary])
    (out / 'program.hex').write_text('@0\n' + '\n'.join(f'{b:02x}' for b in binary.read_bytes()) + '\n')
    return symbols

def inspect_trace(rows, config):
    live = {'instruction': {}, 'data': {}}
    prev = {}
    stats = dict(i_stalls=0, d_stalls=0, redirects=0, stale_error_responses=0, redirect_with_stalled_i=0,
                 redirect_with_pending_i=0, drained=0, simultaneous_requests=0)
    for prefix in ('i', 'd'):
        for name in ('accepted','completed','errors','request_wait','response_wait','response_backpressure'):
            stats[prefix+'_'+name] = 0
    dropped = set()
    obsolete_offered = None
    drain_ack = False
    for row in rows:
        cycle = row['cycle']
        assert row['schema_version'] == 2
        if row['redirect']['valid']:
            stats['redirects'] += 1
            if row['ports']['instruction']['req_valid'] and not row['ports']['instruction']['req_ready']:
                stats['redirect_with_stalled_i'] += 1
                obsolete_offered = (row['ports']['instruction']['req_id'], row['ports']['instruction']['req_addr'])
            if live['instruction']:
                stats['redirect_with_pending_i'] += 1
                dropped.update(live['instruction'])
        if all(row['ports'][p]['req_accepted'] for p in live): stats['simultaneous_requests'] += 1
        for port, transactions in live.items():
            p = row['ports'][port]
            prefix = 'i' if port == 'instruction' else 'd'
            stats[prefix+'_accepted'] += p['req_accepted']
            stats[prefix+'_completed'] += p['resp_accepted']
            stats[prefix+'_errors'] += bool(p['resp_accepted'] and p['resp_error'])
            stats[prefix+'_request_wait'] += bool(p['req_valid'] and not p['req_ready'])
            stats[prefix+'_response_wait'] += bool(transactions and not p['resp_valid'])
            stats[prefix+'_response_backpressure'] += bool(p['resp_valid'] and not p['resp_ready'])
            old = prev.get(port)
            payload = lambda x: tuple(x[k] for k in ('req_id','req_addr','req_write','req_size','req_wdata','req_wstrb','req_memtype','req_priv'))
            if old and old['req_valid'] and not old['req_ready']:
                assert p['req_valid'] and payload(p) == payload(old), f'{port}: stalled request changed at {cycle}'
            if old and old['resp_valid'] and not old['resp_ready']:
                assert p['resp_valid'] and all(p[k] == old[k] for k in ('resp_id','resp_rdata','resp_error')), 'response changed'
            assert p['req_accepted'] == (p['req_valid'] and p['req_ready'])
            assert p['resp_accepted'] == (p['resp_valid'] and p['resp_ready'])
            if p['req_valid'] and not p['req_ready']: stats['i_stalls' if port == 'instruction' else 'd_stalls'] += 1
            if p['resp_valid']:
                assert p['resp_id'] in transactions, f'{port}: unsolicited response'
                issued, addr = transactions[p['resp_id']]
                assert cycle-issued >= config['i_latency' if port == 'instruction' else 'd_latency']
                assert p['owner_addr'] == addr
            if p['resp_accepted']:
                if port == 'instruction' and p['resp_error'] and p['resp_id'] in dropped:
                    stats['stale_error_responses'] += 1
                transactions.pop(p['resp_id'])
                if port == 'instruction': dropped.discard(p['resp_id'])
            if p['req_accepted']:
                assert p['req_id'] not in transactions, 'live ID reused'
                assert not transactions, 'blocking profile exceeded one outstanding'
                transactions[p['req_id']] = (cycle, p['req_addr'])
                if port == 'instruction':
                    if row['redirect']['valid'] or obsolete_offered == (p['req_id'], p['req_addr']):
                        dropped.add(p['req_id'])
                    obsolete_offered = None
            prev[port] = p
        if not row['drain']['requested']: drain_ack = False
        elif drain_ack: assert row['drain']['done'], 'drain acknowledgement dropped before request release'
        if row['drain']['requested'] and row['drain']['done']:
            drain_ack = True
            assert not live['instruction'] and not live['data'], 'drain acknowledged with live transaction'
            assert not row['ports']['instruction']['req_valid'] and not row['ports']['data']['req_valid'], 'drain dropped offered request'
            stats['drained'] += 1
    return stats

def cpu_case(binary, dest, body, config, fault=None, extra=None, check=None):
    symbols = compile_program(dest, body)
    command = [binary, f'+program={dest / "program.hex"}', f'+tohost={symbols["tohost"]:x}',
               f'+signature_begin={symbols["scratch"]:x}', f'+signature_end={symbols["scratch"]+8:x}',
               f'+dump_file={dest / "memory.txt"}', f'+result_file={dest / "metrics.json"}',
               f'+trace_file={dest / "trace.jsonl"}', '+trace_limit=30000', '+timeout=30000']
    command += [f'+{k}={v}' for k,v in config.items()]
    if fault:
        cause, pc, value = fault(symbols)
        command += [f'+expected_trap_cause={cause}', f'+expected_trap_pc={pc:x}', f'+expected_trap_value={value:x}']
    if extra: command += extra(symbols)
    for name in ('metrics.json','memory.txt','trace.jsonl'): (dest/name).unlink(missing_ok=True)
    rc, log = lab.invoke(command, dest / 'run.log', timeout=30)
    assert rc == 0, f'CPU run failed ({rc}): {log[-1200:]}'
    metrics = json.loads((dest / 'metrics.json').read_text())
    assert metrics['status'] == 'pass', metrics
    rows = [json.loads(x) for x in (dest / 'trace.jsonl').read_text().splitlines()]
    coverage = inspect_trace(rows, config)
    for name, value in metrics['memory_counts'].items():
        if name in coverage:
            assert coverage[name] == value, f'{name}: trace={coverage[name]} summary={value}'
    memory = [int(x,16) for x in (dest/'memory.txt').read_text().split()]
    if fault:
        assert metrics['reason'] == 'expected_trap'
        assert not any(r['commit']['valid'] and r['commit']['pc'] == metrics['trap_pc'] for r in rows), 'faulting instruction retired'
    if check: check(metrics, rows, memory, symbols, coverage)
    return {'command': list(map(str,command)), 'elf_sha256': lab.digest(dest/'program.elf'), 'metrics': metrics, 'coverage': coverage}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=lab.BUILD/'memory_protocol.json')
    parser.add_argument('--rtl-dir', type=Path, default=os.environ.get('LAB_RTL_DIR'))
    parser.add_argument('--preset', dest='core_preset', choices=core_config.PRESETS, default=os.environ.get('LAB_CORE_PRESET', 'ant_j0'))
    parser.add_argument('--memory-adapter', choices=core_config.MEMORY_ADAPTERS, default=os.environ.get('LAB_MEMORY_ADAPTER', 'ii1'))
    args = parser.parse_args()
    rtl = args.rtl_dir.resolve() if args.rtl_dir else ROOT/'rtl'
    cpu_config = core_config.resolve(args.core_preset, args.memory_adapter, rtl)
    out = args.output.resolve().parent / 'memory_protocol_cases'
    out.mkdir(parents=True, exist_ok=True)
    report = {'schema_version': 1, 'status': 'fail', 'cases': [], 'scope': 'blocking memory-v1 profile; no IRQ/cache/multiple-ID concurrency claims',
              'core_configuration': cpu_config, 'configuration_sha256': core_config.configuration_sha256(cpu_config),
              'rtl_source_hash': core_config.source_hash(rtl)}
    lab.save_json(args.output, report)
    def record(name, work):
        case = {'name': name, 'passed': False}
        try: case.update(work());case['passed']=True
        except Exception as e: case['error']=str(e)
        report['cases'].append(case)
        lab.save_json(args.output, report)
        print(('PASS ' if case['passed'] else 'FAIL ')+name+('' if case['passed'] else ': '+case['error']), flush=True)
    try:
        ram_binary, report['ram_build'] = build_standalone(rtl, out, cpu_config)
        for name, config in [('ram_latency1', dict(i_latency=1,d_latency=1,i_interval=1,d_interval=1,stall_seed=1,stall_max=0)),
                             ('ram_latency3',dict(i_latency=3,d_latency=3,i_interval=7,d_interval=9,stall_seed=1,stall_max=0)),
                             ('ram_latency5_stalls',dict(i_latency=5,d_latency=5,i_interval=2,d_interval=3,stall_seed=17,stall_max=7))]:
            def work(name=name,config=config):
                result=out/f'{name}.json';result.unlink(missing_ok=True)
                command=[ram_binary,f'+result_file={result}','+i_error_addr=80000040','+d_error_addr=80000020','+d_error_write=1','+error_once=1']+[f'+{k}={v}' for k,v in config.items()]
                lab.require(command,out/f'{name}.log',timeout=30)
                return {'command':list(map(str,command)), **json.loads(result.read_text())}
            record(name,work)
        hardware, key=lab.build_hardware(argparse.Namespace(rtl_dir=str(rtl), core_preset=args.core_preset, memory_adapter=args.memory_adapter))
        report['cpu_build']={'key':key,'identity':json.loads((hardware.parent/'build.json').read_text())}
        fast=dict(i_latency=1,d_latency=1,i_interval=1,d_interval=1,stall_seed=1,stall_max=0)
        stress=dict(i_latency=5,d_latency=3,i_interval=2,d_interval=13,stall_seed=17,stall_max=7)
        def case(name,body,config=stress,**kw): record(name,lambda:cpu_case(hardware,out/name,body,config,**kw))
        def unchanged(m,r,mem,s,c): assert mem==[0x12345678,0x87654321], 'failed operation changed SRAM'
        def no_data(m,r,mem,s,c):
            unchanged(m,r,mem,s,c)
            assert m['memory_counts']['d_accepted']==0, 'unsupported misalignment escaped onto data bus'
        case('instruction_access_fault','nop\n',fault=lambda s:(1,BASE,BASE),extra=lambda s:['+i_error_addr=80000000'],check=no_data)
        case('load_access_fault','la t0,scratch\nfault: lw t1,0(t0)\n',fault=lambda s:(5,s['fault'],s['scratch']),extra=lambda s:[f'+d_error_addr={s["scratch"]:x}','+d_error_write=0'],check=unchanged)
        case('store_access_fault','la t0,scratch\nli t1,0xdeadbeef\nfault: sw t1,0(t0)\n',fault=lambda s:(7,s['fault'],s['scratch']),extra=lambda s:[f'+d_error_addr={s["scratch"]:x}','+d_error_write=1'],check=unchanged)
        case('load_bounds_fault','li t0,0x90000000\nfault: lw t1,0(t0)\n',fault=lambda s:(5,s['fault'],0x90000000),check=unchanged)
        case('store_bounds_fault','li t0,0x90000000\nfault: sw t1,0(t0)\n',fault=lambda s:(7,s['fault'],0x90000000),check=unchanged)
        case('misaligned_load_before_bus','la t0,scratch\nfault: lw t1,1(t0)\n',fault=lambda s:(4,s['fault'],s['scratch']+1),check=no_data)
        case('misaligned_store_before_bus','la t0,scratch\nfault: sh t1,1(t0)\n',fault=lambda s:(6,s['fault'],s['scratch']+1),check=no_data)
        case('illegal_load_encoding_before_bus','fault: .word 0x00003003\n',fault=lambda s:(2,s['fault'],0x00003003),check=no_data)
        case('illegal_store_encoding_before_bus','fault: .word 0x00003023\n',fault=lambda s:(2,s['fault'],0x00003023),check=no_data)
        case('misaligned_jump_before_bus','fault: jal x0,target+2\nnop\ntarget: nop\n',fault=lambda s:(0,s['fault'],s['target']+2),check=no_data)
        body='li t0,12345\nli t1,7\ndiv t2,t0,t1\nj target\nstale: .word 0xffffffff\ntarget: nop\n'
        if cpu_config['memory_directed_revision'] == 'unpredicted_jalr_v2':
            # An early-predicted JAL cannot exercise a stale sequential response.
            # Keep the original assertions and induce the redirect with JALR.
            body='li t0,12345\nli t1,7\nla t3,target\ndiv t2,t0,t1\njalr x0,0(t3)\nstale: .word 0xffffffff\ntarget: nop\n'
        def stale_checked(m,r,mem,s,c):
            assert c['stale_error_responses']>0, 'test did not observe obsolete instruction error response'
            assert not any(x['execute']['valid'] and x['execute']['pc']==s['stale'] for x in r), 'obsolete instruction executed'
        case('redirect_discards_late_instruction_fault',body,extra=lambda s:[f'+i_error_addr={s["stale"]:x}'],check=stale_checked)
        # Long request stalls independently cover held requests on redirect. Several
        # deterministic seeds are retained as evidence; at least one must hit it.
        stalled=[]
        for seed in (1,17,39):
            cfg=dict(stress,stall_seed=seed,stall_max=60,
                     i_interval=41 if cpu_config['memory_adapter']=='ii1' else 1)
            def work(seed=seed,cfg=cfg):
                value=cpu_case(hardware,out/f'redirect_stalled_seed{seed}',body,cfg,
                               extra=lambda s:[f'+i_error_addr={s["stale"]:x}'])
                if value['coverage']['redirect_with_stalled_i']:
                    assert value['coverage']['stale_error_responses'] > 0, 'held obsolete request did not drain its error response'
                stalled.append(value['coverage']['redirect_with_stalled_i'])
                return value
            record(f'redirect_stalled_seed{seed}',work)
        record('redirect_stalled_request_coverage',lambda: {'observed':sum(stalled)} if sum(stalled)>0 else (_ for _ in ()).throw(AssertionError('no redirect crossed an offered/stalled instruction request')))
        def drained(m,r,mem,s,c):
            assert m['drain_count']==1 and c['drained']>=2, 'drain did not complete and remain acknowledged'
            assert any(x['commit']['valid'] and x['commit']['pc']==s['finish'] for x in r), 'execution did not resume after drain'
        case('drain_offered_instruction','nop\nnop\nnop\n',config=dict(stress,stall_seed=7,stall_max=20),extra=lambda s:['+drain_when_i_stalled=1','+drain_hold=4'],check=drained)
        case('drain_offered_data','la t0,scratch\nlw t1,0(t0)\nsw t1,4(t0)\n',config=dict(stress,d_interval=100,stall_max=9),extra=lambda s:['+drain_when_d_stalled=1','+drain_hold=4'],check=drained)
    except Exception as e: report['setup_error']=str(e)
    report['status']='pass' if report['cases'] and all(x['passed'] for x in report['cases']) and 'setup_error' not in report else 'fail'
    report['passed']=report['status']=='pass'
    lab.save_json(args.output,report)
    print(f'Memory protocol: {report["status"].upper()} ({sum(c["passed"] for c in report["cases"])}/{len(report["cases"])})')
    if 'setup_error' in report: print(report['setup_error'])
    return 0 if report['passed'] else 1

if __name__=='__main__': raise SystemExit(main())
