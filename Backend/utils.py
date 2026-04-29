import time
import os
import uuid as uuid_module


def generate_uuid7() -> uuid_module.UUID:
    """
    Generate a UUID version 7 (time-ordered) per RFC 9562.
    Structure:
      bits 127-80 : unix_ts_ms  (48 bits)
      bits 79-76  : version = 7  (4 bits)
      bits 75-64  : rand_a       (12 bits)
      bits 63-62  : variant = 10 (2 bits)
      bits 61-0   : rand_b       (62 bits)
    """
    ms = int(time.time() * 1000)
    rand_bytes = os.urandom(10)  # 80 random bits
    rand_int = int.from_bytes(rand_bytes, "big")
    rand_a = (rand_int >> 68) & 0xFFF          # top 12 bits
    rand_b = rand_int & ((1 << 62) - 1)        # bottom 62 bits

    uuid_int = (
        (ms << 80)
        | (0x7 << 76)
        | (rand_a << 64)
        | (0b10 << 62)
        | rand_b
    )
    return uuid_module.UUID(int=uuid_int)
