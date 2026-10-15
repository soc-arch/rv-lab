# =============================================================================
# HY-RV | filelist
# Description: Ordered SystemVerilog compilation source list.
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

common/rv_trace_pkg.sv
compat/teaching_trace_pkg.sv
common/rv_bp_pkg.sv
common/insn_supply_if.sv
common/mem_if.sv
common/rv32_decoder.sv
common/rv32_alu_op_decode.sv
common/rv32_ls_split.sv
common/rv32_ls_align2.sv
common/rv32_rf.sv
common/rv32_pmu.sv
common/rv32_csr.sv
common/fu_alu.sv
common/fu_br.sv
common/fu_mul.sv
common/fu_div.sv
frontend/gen_pc_nxt.sv
frontend/fetch_ctrl.sv
frontend/fetch_tracker.sv
frontend/rv_branch_predecode.sv
frontend/rv_bp_policy.sv
frontend/rv_branch_predictor.sv
frontend/insn_assemble.sv
frontend/rv_frontend.sv
common/rv_insn_link.sv
simple/rv_backend.sv
simple/rv_core_simple.sv
compat/teaching_cpu.sv
