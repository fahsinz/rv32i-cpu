"""Assemble a program for the FPGA and say what the board should show.

    python tools/build_program.py                    # fpga/program.s -> fpga/program.hex
    python tools/build_program.py --run              # also run it on the golden model

The .hex is what $readmemh loads into the memory array at power-up. Running it
on the model first means you know the expected answer before you look at the
board, which is the difference between testing and hoping.
"""

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from verif.asm import assemble, to_hex  # noqa: E402
from verif.iss import Iss  # noqa: E402

HALT_NAMES = {0: "still running", 1: "ECALL", 2: "EBREAK", 3: "illegal instruction",
              4: "misaligned load/store", 5: "misaligned instruction fetch"}
ABI = {10: "a0", 11: "a1", 12: "a2", 5: "t0", 6: "t1", 7: "t2"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", default=str(REPO / "fpga" / "program.s"))
    parser.add_argument("-o", "--output", default=str(REPO / "fpga" / "program.hex"))
    parser.add_argument("--words", type=int, default=256, help="memory size of the target build")
    parser.add_argument("--run", action="store_true", help="run on the golden model and report")
    args = parser.parse_args()

    source = Path(args.source)
    words = assemble(source.read_text())
    if len(words) > args.words:
        raise SystemExit(f"program is {len(words)} words, target memory holds {args.words}")
    Path(args.output).write_text(to_hex(words))

    print(f"{source.name}: {len(words)} instructions -> {Path(args.output).name}")
    for i, word in enumerate(words):
        print(f"  0x{i * 4:04x}  {word:08x}")

    if args.run:
        iss = Iss(words, words=args.words)
        trace = iss.run()
        print(f"\nmodel: {len(trace)} instructions retired, "
              f"halted on {HALT_NAMES.get(iss.halt_cause, iss.halt_cause)}")
        print("registers the board should show:")
        for r in range(32):
            if iss.regs[r]:
                name = ABI.get(r, f"x{r}")
                print(f"  x{r:<2} {name:<3} = 0x{iss.regs[r]:08x}  ({iss.regs[r]})")
        touched = [(i, v) for i, v in enumerate(iss.mem) if v and i >= len(words)]
        if touched:
            print("memory written by the program:")
            for i, v in touched:
                print(f"  0x{i * 4:04x} = 0x{v:08x}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
