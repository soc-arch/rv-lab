    .text
    .globl main
main:
    addi sp, sp, -16
    sw ra, 12(sp)
    li t0, 4
    li t1, 0
sum_loop:
    add t1, t1, t0
    addi t0, t0, -1
    bne t0, zero, sum_loop
    li a0, 20
    mv a1, t1
    li a2, 10
    call lab_check
    li a0, 21
    call get_answer
    mv a1, a0
    li a0, 21
    li a2, 42
    call lab_check
    li a0, 0
    lw ra, 12(sp)
    addi sp, sp, 16
    ret
get_answer:
    slli a0, a0, 1
    ret
