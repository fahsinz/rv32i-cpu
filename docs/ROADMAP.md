# Roadmap (Days 12–21)

| Day | Milestone | Deliverables |
|-----|-----------|--------------|
| 12 | **Building blocks** (done) | Repo + toolchain, `alu`, `regfile`, `imm_gen`, cocotb unit tests driven by pytest |
| 13 | **Decode & memory** (done) | Main decoder / control, branch comparator, PC-next logic, unified byte-addressed memory (LB/LH/LW/LBU/LHU, SB/SH/SW) |
| 14 | **Single-cycle core** (done) | Datapath integration, halt on ECALL/EBREAK/illegal, RVFI-style commit trace port |
| 15 | **Programs** (done) | Python RV32I assembler + hex loader, directed test per instruction, first real programs (Fibonacci, bubble sort) |
| 16 | **Golden model** (done) | Independent Python instruction-set simulator (ISS) of RV32I, self-checked on the directed programs |
| 17 | **Verification env** (done) | cocotb commit monitor + scoreboard: every retired instruction compared against the ISS (pc, inst, rd, rd value, mem writes, next pc) |
| 18 | **Constrained random** (done) | Random instruction-stream generator (legal encodings, bounded branches, memory-safe loads/stores), seeded regressions |
| 19 | **Coverage** (done) | Functional coverage (opcode × x0 cases, branch taken/not-taken, signed extremes, shift amounts, load/store widths) + report |
| 20 | **Proof it works** (done) | Bug-injection campaign showing the scoreboard catches each mutation, GitHub Actions CI |
| 21 | **Polish** (done) | Block diagram, verification plan, results, waveforms in README |

All 21 days complete. The hardware walkthrough lives in [HARDWARE.md](HARDWARE.md).
