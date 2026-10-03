# Program that runs on the DE10-Lite.
#
# Sums 1..10, leaves the answer in a0 (x10), stores it to 0x80, then halts
# with ECALL. Watch it with SW[8]=1 and SW[4:0]=10: HEX shows 0x000037 = 55.

        li   a0, 0              # running total
        li   t0, 1              # counter
        li   t1, 11             # limit
loop:
        add  a0, a0, t0
        addi t0, t0, 1
        blt  t0, t1, loop
        li   t2, 0x80           # also park the result in memory
        sw   a0, 0(t2)
        ecall                   # halt, cause 1
