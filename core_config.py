# =============================================================================
# HY-RV | core_config
# Description: Select actual CPU elaboration parameters and memory-adapter identities.
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

"""One configuration contract for application and independent memory tests."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
PRESETS = ("ant_j0", "ant_j1", "btfnt_j0", "btfnt_j1")
MEMORY_ADAPTERS = ("ii1", "frozen")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rtl_identity(rtl):
    """Hash the ordered compilation list and its sources using canonical names."""
    rtl = Path(rtl).resolve()
    paths = [rtl / "filelist.f"]
    for line in paths[0].read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        path = (rtl / line).resolve()
        path.relative_to(rtl)  # Reject source-list escape and ambiguous receipts.
        paths.append(path)
    paths += [p for p in rtl.rglob("*") if p.suffix in (".svh", ".vh")]
    return {str(p.relative_to(rtl)): digest(p) for p in sorted(set(paths))}


def source_hash(rtl):
    return hashlib.sha256(json.dumps(rtl_identity(rtl), sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def configuration_sha256(config):
    """Match canonical configuration-file bytes, including the final newline."""
    return hashlib.sha256((json.dumps(config, indent=2) + "\n").encode()).hexdigest()


def adapter_path(memory_adapter=None):
    adapter = memory_adapter or os.environ.get("LAB_MEMORY_ADAPTER") or "ii1"
    if adapter not in MEMORY_ADAPTERS:
        raise ValueError(f"Unknown memory adapter {adapter!r}; choose {MEMORY_ADAPTERS}")
    return (ROOT / "tb/teaching_sram.sv" if adapter == "ii1" else
            ROOT / "reference/legacy_teaching_51562ce/tb/teaching_sram.sv")


def resolve(preset=None, memory_adapter=None, rtl=None):
    preset = preset or os.environ.get("LAB_CORE_PRESET") or "ant_j0"
    adapter = memory_adapter or os.environ.get("LAB_MEMORY_ADAPTER") or "ii1"
    if preset not in PRESETS:
        raise ValueError(f"Unknown core preset {preset!r}; choose {PRESETS}")
    adapter_path(adapter)
    rtl = Path(rtl or ROOT / "rtl").resolve()
    identity = rtl_identity(rtl)
    wrappers = [rtl / name for name in identity if name.endswith("teaching_cpu.sv")]
    wrapper = wrappers[0].read_text() if wrappers else ""
    parameterized = bool(re.search(r"parameter[^;]*\bBP_PROFILE\s*=", wrapper))
    if not parameterized:
        # Preserve the public replacement ABI for a parameterless student CPU.
        # Such a source is never represented as the verified P1 preset.
        if preset != "ant_j0":
            raise ValueError("This replacement CPU has no P1 static-profile parameters; use ant_j0 for its public-contract test")
        return {"schema_version": 1, "model_id": "external_memory_v1_cpu",
                "display_name": "External memory-v1 CPU", "preset": "external",
                "parameters": {}, "effective_parameters": {"RESET_PC": "0x80000000"},
                "configuration_status": "parameterless_public_contract",
                "memory_adapter": adapter, "memory_directed_revision": "original",
                "held_redirect_timing_revision": "i_interval41_v1" if adapter == "ii1" else "original",
                "compile_flags": ["+define+HY_RV_PARAMETERLESS_CORE=1"]}
    bp = int(preset.startswith("btfnt"))
    early = int(preset.endswith("j1"))
    params = dict(BP_PROFILE=bp, COND_POLICY=bp, EARLY_JAL_EN=early, INSN_QUEUE_DEPTH=0)
    defaults = {name: int(match.group(1)) for name in
                ("BP_PROFILE", "COND_POLICY", "EARLY_JAL_EN", "INSN_QUEUE_DEPTH",
                 "STATIC_POLICY_EN", "SUCCESSOR_CHECK_EN")
                if (match := re.search(rf"\b{name}\s*=\s*([01])\b", wrapper.split(") (")[0]))}
    return {"schema_version": 1, "bp_numbering_version": "bp-profiles-v2",
            "model_id": f"p1_f0_bp{bp}_ls0_x1", "display_name": f"HY-RV P1.F0.BP{bp}.LS0.X1",
            "preset": preset, "parameters": params, "source_parameter_defaults": defaults,
            "effective_parameters": dict(defaults, **params, RESET_PC="0x80000000"),
            "configuration_status": "elaboration_parameters", "memory_adapter": adapter,
            "memory_directed_revision": "unpredicted_jalr_v2" if early and defaults.get("STATIC_POLICY_EN") else "original",
            "held_redirect_timing_revision": "i_interval41_v1" if adapter == "ii1" else "original",
            "compile_flags": [f"+define+HY_RV_{name}={value}" for name, value in params.items()]}
