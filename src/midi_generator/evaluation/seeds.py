"""Deterministic seed derivation for candidate generation."""

import random


def derive_seeds(base_seed: int, count: int) -> tuple[int, ...]:
    """Return ``count`` distinct seeds derived only from ``base_seed``.

    The sequence depends exclusively on ``random.Random(base_seed)`` so it is
    bit-exact and independent of global random state. Duplicates drawn from the
    31-bit space are skipped, keeping the result stable and collision-free.
    """
    if count < 1:
        raise ValueError("count must be at least 1.")

    rng = random.Random(base_seed)
    seeds: list[int] = []
    seen: set[int] = set()
    while len(seeds) < count:
        candidate = rng.getrandbits(31)
        if candidate in seen:
            continue
        seen.add(candidate)
        seeds.append(candidate)
    return tuple(seeds)
