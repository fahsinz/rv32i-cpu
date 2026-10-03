"""Bug injection: plant a known bug in a copy of the RTL and require the tests to fail.

A passing test suite proves nothing on its own. This plants one specific bug at
a time in a scratch copy of the design, runs the tests that should notice, and
reports any bug that slipped through. Files in rtl/ are never modified.

    python tools/inject_bugs.py                 # every bug
    python tools/inject_bugs.py --only core     # just the ones matching "core"
    python tools/inject_bugs.py --list
"""

import argparse
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from cocotb_tools.runner import get_results, get_runner  # noqa: E402

BLOCKS = {
    "alu": (["alu.sv"], "verif.unit.tb_alu", {}),
    "regfile": (["regfile.sv"], "verif.unit.tb_regfile", {}),
    "imm_gen": (["imm_gen.sv"], "verif.unit.tb_imm_gen", {}),
    "decoder": (["decoder.sv"], "verif.unit.tb_decoder", {}),
    "branch_cmp": (["branch_cmp.sv"], "verif.unit.tb_branch_cmp", {}),
    "memory": (["memory.sv"], "verif.unit.tb_memory", {"WORDS": 256}),
    "pc_unit": (["pc_unit.sv"], "verif.unit.tb_pc_unit", {}),
    "soc": (["alu.sv", "regfile.sv", "imm_gen.sv", "decoder.sv", "branch_cmp.sv",
             "memory.sv", "pc_unit.sv", "core.sv", "soc.sv"], "verif.tb_core", {"WORDS": 1024}),
}


@dataclass
class Mutant:
    target: str          # which entry of BLOCKS to build and test
    file: str            # file in rtl/ to corrupt
    description: str
    old: str
    new: str
    extra: list[tuple[str, str]] = field(default_factory=list)  # further edits in the same file


MUTANTS = [
    # ---------------------------------------------------------------- alu
    Mutant("alu", "alu.sv", "SRA does a logical shift",
           "ALU_SRA:  y = $signed(a) >>> shamt;", "ALU_SRA:  y = a >> shamt;"),
    Mutant("alu", "alu.sv", "SLT compares unsigned",
           "ALU_SLT:  y = {31'b0, $signed(a) < $signed(b)};", "ALU_SLT:  y = {31'b0, a < b};"),
    Mutant("alu", "alu.sv", "shift amount uses 6 bits",
           "logic [4:0] shamt;\n  assign shamt = b[4:0];", "logic [5:0] shamt;\n  assign shamt = b[5:0];"),
    # ------------------------------------------------------------ regfile
    Mutant("regfile", "regfile.sv", "rs2 port reads the rs1 address",
           "regs[rs2_addr];", "regs[rs1_addr];"),
    Mutant("regfile", "regfile.sv", "reset does not clear the registers",
           "for (int i = 0; i < 32; i++) regs[i] <= 32'b0;", ";"),
    Mutant("regfile", "regfile.sv", "both x0 guards removed",
           "if (we && rd_addr != 5'd0) begin", "if (we) begin",
           [("assign rs1_data = (rs1_addr == 5'd0) ? 32'b0 : regs[rs1_addr];",
             "assign rs1_data = regs[rs1_addr];")]),
    # ------------------------------------------------------------ imm_gen
    Mutant("imm_gen", "imm_gen.sv", "B-type reads inst[12:9] instead of inst[11:8]",
           "inst[30:25], inst[11:8], 1'b0}", "inst[30:25], inst[12:9], 1'b0}"),
    Mutant("imm_gen", "imm_gen.sv", "J-type bit 11 taken from inst[21]",
           "inst[19:12], inst[20], inst[30:21]", "inst[19:12], inst[21], inst[30:21]"),
    Mutant("imm_gen", "imm_gen.sv", "S-type not sign-extended",
           "IMM_S:   imm = {{20{inst[31]}}", "IMM_S:   imm = {{20{1'b0}}"),
    # ------------------------------------------------------------ decoder
    Mutant("decoder", "decoder.sv", "JALR writes the ALU result, not the link address",
           "          wb_sel    = WB_PC4;\n          jalr      = 1'b1;",
           "          wb_sel    = WB_ALU;\n          jalr      = 1'b1;"),
    Mutant("decoder", "decoder.sv", "LUI adds rs1 instead of zero",
           "        alu_a_sel = ALU_A_ZERO;", "        alu_a_sel = ALU_A_RS1;"),
    Mutant("decoder", "decoder.sv", "store width check removed",
           "if (funct3[2] || funct3[1:0] == 2'b11) illegal   = 1'b1;",
           "if (1'b0)                              illegal   = 1'b1;"),
    Mutant("decoder", "decoder.sv", "R-type funct7 never validated",
           "        if (funct7 != 7'b0000000 &&\n            !(funct7 == 7'b0100000 && (funct3 == 3'b000 || funct3 == 3'b101))) illegal = 1'b1;",
           "        if (1'b0) illegal = 1'b1;"),
    Mutant("decoder", "decoder.sv", "illegal instructions keep their side effects",
           "    if (illegal) begin\n      reg_write = 1'b0;", "    if (1'b0) begin\n      reg_write = 1'b0;"),
    Mutant("decoder", "decoder.sv", "SRAI decoded as SRLI",
           "        alu_op = (funct3 == 3'b101) ? {funct7[5], funct3} : {1'b0, funct3};",
           "        alu_op = {1'b0, funct3};"),
    Mutant("decoder", "decoder.sv", "EBREAK matched on the wrong funct12",
           "inst[31:20] == 12'h001", "inst[31:20] == 12'h002"),
    # --------------------------------------------------------- branch_cmp
    Mutant("branch_cmp", "branch_cmp.sv", "BGE compares unsigned",
           "3'b101:  taken = ($signed(a) >= $signed(b));", "3'b101:  taken = (a >= b);"),
    Mutant("branch_cmp", "branch_cmp.sv", "BLTU compares signed",
           "3'b110:  taken = (a < b);", "3'b110:  taken = ($signed(a) < $signed(b));"),
    Mutant("branch_cmp", "branch_cmp.sv", "unused funct3 branches instead of never taking",
           "default: taken = 1'b0;", "default: taken = 1'b1;"),
    # ------------------------------------------------------------- memory
    Mutant("memory", "memory.sv", "LB does not sign-extend",
           "3'b000:  d_rdata = {{24{lane_b[7]}}, lane_b};", "3'b000:  d_rdata = {24'b0, lane_b};"),
    Mutant("memory", "memory.sv", "LH does not sign-extend",
           "3'b001:  d_rdata = {{16{lane_h[15]}}, lane_h};", "3'b001:  d_rdata = {16'b0, lane_h};"),
    Mutant("memory", "memory.sv", "halfword lane picked by the wrong address bit",
           "lane_h = off[1] ? word[31:16] : word[15:0];", "lane_h = off[0] ? word[31:16] : word[15:0];"),
    Mutant("memory", "memory.sv", "SB always writes byte lane 0",
           "3'b000:  byte_en = 4'b0001 << off;", "3'b000:  byte_en = 4'b0001;"),
    Mutant("memory", "memory.sv", "SH does not replicate data to the high lane",
           "3'b001:  wdata_lanes = {2{d_wdata[15:0]}};", "3'b001:  wdata_lanes = d_wdata;"),
    Mutant("memory", "memory.sv", "word accesses only check address bit 0",
           "3'b010:         unaligned = |d_addr[1:0];", "3'b010:         unaligned = d_addr[0];"),
    Mutant("memory", "memory.sv", "misaligned stores are not blocked",
           "if (d_write && !d_misaligned) mem[d_index] <= merged;", "if (d_write) mem[d_index] <= merged;"),
    Mutant("memory", "memory.sv", "instruction port indexes by halfword",
           "assign i_index = i_addr[IDX_BITS+1:2];", "assign i_index = i_addr[IDX_BITS:1];"),
    # ------------------------------------------------------------ pc_unit
    Mutant("pc_unit", "pc_unit.sv", "PC advances by 8",
           "assign pc_plus4 = pc + 32'd4;", "assign pc_plus4 = pc + 32'd8;"),
    Mutant("pc_unit", "pc_unit.sv", "JALR does not clear bit 0",
           "if (jalr)                        pc_next = {alu_result[31:1], 1'b0};",
           "if (jalr)                        pc_next = alu_result;"),
    Mutant("pc_unit", "pc_unit.sv", "branches ignore the comparator",
           "else if (jump || (branch && taken)) pc_next = pc + imm;",
           "else if (jump || branch) pc_next = pc + imm;"),
    Mutant("pc_unit", "pc_unit.sv", "stall ignored",
           "else if (!stall) pc <= pc_next;", "else             pc <= pc_next;"),
    Mutant("pc_unit", "pc_unit.sv", "misaligned target only checks bit 0",
           "assign misaligned_target = |pc_next[1:0];", "assign misaligned_target = pc_next[0];"),
    # ---------------------------------------------------- core integration
    Mutant("soc", "core.sv", "core: write-back takes the ALU result instead of memory",
           "      WB_MEM:  wb_data = d_rdata;", "      WB_MEM:  wb_data = alu_y;"),
    Mutant("soc", "core.sv", "core: stores send rs1 instead of rs2",
           "  assign d_wdata = rs2_data;", "  assign d_wdata = rs1_data;"),
    Mutant("soc", "core.sv", "core: ALU operand B mux inverted",
           "  assign alu_b = (alu_b_sel == ALU_B_IMM) ? imm : rs2_data;",
           "  assign alu_b = (alu_b_sel == ALU_B_IMM) ? rs2_data : imm;"),
    Mutant("soc", "core.sv", "core: branch comparator operands swapped",
           "    .a      (rs1_data),\n    .b      (rs2_data),", "    .a      (rs2_data),\n    .b      (rs1_data),"),
    Mutant("soc", "core.sv", "core: rs2 read from the rs1 field",
           "    .rs2_addr (inst[24:20]),", "    .rs2_addr (inst[19:15]),"),
    Mutant("soc", "core.sv", "core: a trapping instruction still writes its register",
           "    .we       (reg_write && !halted && !trap),", "    .we       (reg_write && !halted),"),
    Mutant("soc", "core.sv", "core: PC is not held on a trap",
           "    .stall             (halted || trap),", "    .stall             (halted),"),
    Mutant("soc", "core.sv", "core: AUIPC uses rs1 instead of the PC",
           "      ALU_A_PC:   alu_a = pc;", "      ALU_A_PC:   alu_a = rs1_data;"),
    Mutant("soc", "core.sv", "core: JAL links to the PC instead of PC+4",
           "      WB_PC4:  wb_data = pc_plus4;", "      WB_PC4:  wb_data = pc;"),
    Mutant("soc", "core.sv", "core: step_en ignored by the PC, so it cannot be held",
           "    .stall             (halted || trap || !step_en),", "    .stall             (halted || trap),"),
    Mutant("soc", "core.sv", "core: step_en ignored by register writes",
           "    .we       (reg_write && !halted && !trap && step_en),",
           "    .we       (reg_write && !halted && !trap),"),
]


def run_mutant(mutant: Mutant, work: Path) -> tuple[int, int]:
    """Build and test one mutant. Returns (tests, failures)."""
    sources, test_module, params = BLOCKS[mutant.target]
    work.mkdir(parents=True)

    shutil.copy(REPO / "rtl" / "rv32i_pkg.sv", work)
    for name in sources:
        shutil.copy(REPO / "rtl" / name, work)

    victim = work / mutant.file
    text = victim.read_text()
    for old, new in [(mutant.old, mutant.new)] + mutant.extra:
        if text.count(old) != 1:
            raise SystemExit(f"pattern not found exactly once in {mutant.file}: {old[:60]!r}")
        text = text.replace(old, new)
    victim.write_text(text)

    runner = get_runner("icarus")
    runner.build(
        sources=[work / "rv32i_pkg.sv"] + [work / n for n in sources],
        hdl_toplevel=mutant.target,
        parameters=params,
        build_dir=work / "build",
        timescale=("1ns", "1ps"),
        always=True,
    )
    results = (work / "results.xml").resolve()
    try:
        runner.test(hdl_toplevel=mutant.target, test_module=test_module,
                    build_dir=work / "build", test_dir=work / "build",
                    results_xml=results, log_file=work / "sim.log")
    except SystemExit:
        pass
    return get_results(results)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", help="run only bugs whose target or description matches this text")
    parser.add_argument("--list", action="store_true", help="list the bugs and exit")
    parser.add_argument("--work", default=None, help="scratch directory (default: build/mutants)")
    args = parser.parse_args()

    selected = [m for m in MUTANTS
                if not args.only or args.only.lower() in f"{m.target} {m.description}".lower()]
    if args.list:
        for m in selected:
            print(f"{m.target:11s} {m.description}")
        return 0
    if not selected:
        print("no bugs matched")
        return 1

    work_root = Path(args.work) if args.work else REPO / "build" / "mutants"
    shutil.rmtree(work_root, ignore_errors=True)

    survivors = []
    for i, mutant in enumerate(selected):
        tests, failures = run_mutant(mutant, work_root / f"m{i:02d}_{mutant.target}")
        status = "KILLED  " if failures else "SURVIVED"
        if not failures:
            survivors.append(mutant)
        print(f"{status} {mutant.target:11s} {failures}/{tests} tests failed  <- {mutant.description}",
              flush=True)

    print(f"\n{len(selected) - len(survivors)}/{len(selected)} injected bugs caught")
    if survivors:
        print("\nSURVIVING BUGS (the tests cannot see these):")
        for m in survivors:
            print(f"  {m.target}: {m.description}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
