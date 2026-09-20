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


def as_int(handle) -> int:
    """Read a DUT signal as an unsigned int.

    Multi-bit ports come back as LogicArray (to_unsigned); 1-bit ports come back
    as a plain Logic, which converts with int().
    """
    value = handle.value
    return value.to_unsigned() if hasattr(value, "to_unsigned") else int(value)
