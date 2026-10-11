/* RV32I positive contract: 58 checks, IDs 200..257.
 * No CSR, ECALL, EBREAK, compressed instructions, or misaligned accesses.
 * The caller provides a 16-byte-aligned stack and lab_check(id, got, want).
 * Ordinary FENCE needs no extra work only when SRAM accesses already obey
 * the required ordering. FENCE.I is a separate extension and is not used.
 */
    .option norvc
    .section .text
    .balign 4
    .globl main
    .type main, @function
    .set check_id, 200

    .macro CHECK reg, expected
        li a0, check_id
        mv a1, \reg
        li a2, \expected
        call lab_check
        .set check_id, check_id + 1
    .endm

    .macro REG_CASE op, lhs, rhs, expected
        li t0, \lhs
        li t1, \rhs
        \op t2, t0, t1
        CHECK t2, \expected
    .endm

    .macro IMM_CASE op, lhs, imm, expected
        li t0, \lhs
        \op t2, t0, \imm
        CHECK t2, \expected
    .endm

    .macro BRANCH_CASE op, lhs, rhs, expected
        li t0, \lhs
        li t1, \rhs
        li t2, 0
        \op t0, t1, .Ltaken\@
        j .Lbranch_done\@
    .Ltaken\@:
        li t2, 1
    .Lbranch_done\@:
        CHECK t2, \expected
    .endm

main:
    addi sp, sp, -16
    sw ra, 12(sp)
    sw s0, 8(sp)
    sw s1, 4(sp)

    /* Register ALU operations: overflow wraps; comparisons distinguish sign. */
    REG_CASE add,  0x7fffffff, 1,          0x80000000
    REG_CASE sub,  0,          1,          0xffffffff
    REG_CASE sll,  1,          31,         0x80000000
    REG_CASE slt,  0x80000001, 1,          1
    REG_CASE sltu, 0x80000001, 1,          0
    REG_CASE xor,  0x5555aaaa, 0xffff0000, 0xaaaaaaaa
    REG_CASE srl,  0x80000001, 1,          0x40000000
    REG_CASE sra,  0x80000001, 1,          0xc0000000
    REG_CASE or,   0xa500005a, 0x00ff3300, 0xa5ff335a
    REG_CASE and,  0xaa55ffff, 0x0ff0f00f, 0x0a50f00f

    /* Immediate ALU operations: ordinary immediates are sign-extended. */
    IMM_CASE addi,  -16,        17,   1
    IMM_CASE slti,  -1,         0,    1
    IMM_CASE sltiu, 1,          -1,   1
    IMM_CASE xori,  0x12345678, -1,   0xedcba987
    IMM_CASE ori,   0x12345678, 0x123,0x1234577b
    IMM_CASE andi,  0x12345678, -16,  0x12345670
    IMM_CASE slli,  1,          31,   0x80000000
    IMM_CASE srli,  0x80000001, 31,   1
    IMM_CASE srai,  0x80000001, 31,   0xffffffff

    /* Register shift counts use only rs2[4:0]. */
    REG_CASE sll, 1,          32, 1
    REG_CASE srl, 0x80000000, 33, 0x40000000
    REG_CASE sra, 0x80000000, 32, 0x80000000

    lui t2, 0xabcde
    CHECK t2, 0xabcde000
.Lpc_anchor:
    auipc t2, 0
    la t0, .Lpc_anchor
    sub t2, t2, t0
    CHECK t2, 0

    li t0, 0x12345678
    add zero, t0, t0
    addi t2, zero, 0
    CHECK t2, 0

    /* Check redirect squash and link PC+4 independently. */
    li t2, 0
    jal t0, .Ljal_target
.Ljal_return:
    addi t2, t2, 1       /* Must be squashed. */
.Ljal_target:
    la t1, .Ljal_return
    sub s1, t0, t1
    CHECK t2, 0
    CHECK s1, 0

    li t2, 0
    la t0, .Ljalr_target
    ori t0, t0, 1        /* JALR must clear target bit zero. */
    jalr t1, 0(t0)
.Ljalr_return:
    addi t2, t2, 1       /* Must be squashed. */
.Ljalr_target:
    la t0, .Ljalr_return
    sub s1, t1, t0
    CHECK t2, 0
    CHECK s1, 0

    /* Each of the six branch conditions is both taken and not taken. */
    BRANCH_CASE beq,  1,  1,  1
    BRANCH_CASE beq,  1,  2,  0
    BRANCH_CASE bne,  1,  2,  1
    BRANCH_CASE bne,  1,  1,  0
    BRANCH_CASE blt, -1,  1,  1
    BRANCH_CASE blt,  1, -1,  0
    BRANCH_CASE bge,  1, -1,  1
    BRANCH_CASE bge, -1,  1,  0
    BRANCH_CASE bltu, 0, -1,  1
    BRANCH_CASE bltu,-1,  0,  0
    BRANCH_CASE bgeu,-1,  0,  1
    BRANCH_CASE bgeu, 0, -1,  0

    /* Little-endian, naturally aligned loads/stores and lane preservation. */
    la s0, .Ldata
    li t0, 0x80ff7f01
    sw t0, 0(s0)
    lw t2, 0(s0)
    CHECK t2, 0x80ff7f01
    lb t2, 0(s0)
    CHECK t2, 1
    lb t2, 1(s0)
    CHECK t2, 127
    lb t2, 2(s0)
    CHECK t2, 0xffffffff
    lb t2, 3(s0)
    CHECK t2, 0xffffff80
    lbu t2, 2(s0)
    CHECK t2, 255
    lbu t2, 3(s0)
    CHECK t2, 128
    lh t2, 0(s0)
    CHECK t2, 0x7f01
    lh t2, 2(s0)
    CHECK t2, 0xffff80ff
    lhu t2, 2(s0)
    CHECK t2, 0x80ff

    li t0, 0xaa
    sb t0, 0(s0)
    lw t2, 0(s0)
    CHECK t2, 0x80ff7faa
    li t0, 0xbb
    sb t0, 1(s0)
    lw t2, 0(s0)
    CHECK t2, 0x80ffbbaa
    li t0, 0xcc
    sb t0, 2(s0)
    lw t2, 0(s0)
    CHECK t2, 0x80ccbbaa
    li t0, 0xdd
    sb t0, 3(s0)
    lw t2, 0(s0)
    CHECK t2, 0xddccbbaa
    li t0, 0x1122
    sh t0, 0(s0)
    lw t2, 0(s0)
    CHECK t2, 0xddcc1122
    li t0, 0x3344
    sh t0, 2(s0)
    lw t2, 0(s0)
    CHECK t2, 0x33441122
    fence rw, rw
    lw t2, 0(s0)
    CHECK t2, 0x33441122

    li a0, 0
    lw s1, 4(sp)
    lw s0, 8(sp)
    lw ra, 12(sp)
    addi sp, sp, 16
    ret
    .size main, .-main

    .if check_id != 258
    .error "Unexpected RV32I contract check count"
    .endif

    .section .bss
    .balign 4
.Ldata:
    .zero 4
