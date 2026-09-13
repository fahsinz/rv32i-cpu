"""Bit-manipulation helpers shared by testbenches and the golden model."""

MASK32 = 0xFFFF_FFFF


def bits(value: int, hi: int, lo: int) -> int:
    """Return value[hi:lo] (inclusive, Verilog-style)."""
    return (value >> lo) & ((1 << (hi - lo + 1)) - 1)


def to_signed(value: int, width: int = 32) -> int:
    """Interpret the low `width` bits of value as a two's-complement integer."""
    value &= (1 << width) - 1
    return value - (1 << width) if value >> (width - 1) else value


def sign_extend(value: int, width: int) -> int:
    """Sign-extend a `width`-bit field to 32 bits, returned as an unsigned int."""
    return to_signed(value, width) & MASK32
