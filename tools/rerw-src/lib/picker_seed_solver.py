"""Offline brute-force seed solver for SkillController_roll_proposed_skills.

Mirrors the inline PCG step + partial Fisher-Yates selection observed in
SkillController_roll_proposed_skills @ image+0x39c300.

PCG step (per draw, in-place on TLS+0xff3c):
    s = (s * 0x2c9277b5 + 0xac564b05) & 0xFFFFFFFF
    s = (s >> (((s >> 28) + 4) & 0x1F)) ^ s
    s = (s * 0x108ef2d9) & 0xFFFFFFFF
    s = (s >> 22) ^ s
    new_state = s & 0x7FFFFFFF        # stored back
    draw      = new_state             # masked value used as the draw

Selection (per pick):
    idx = draw % pool_size
    pick = pool[idx]
    swap pool[idx] with pool[pool_size-1]
    pool_size -= 1

The pool MUST be the ALREADY-PRUNED pool (slot exclusions + modifier-blocked
exclusions + previous-proposal exclusions all applied). Capture it from Frida
right before the draw loop.

Rarity rolls only fire when slot.tier == 4 (uninitialized). If the active
save has all slot tiers set to a real rarity (0..3), no rarity rolls occur
during the picker — the solver only needs to mirror selection.

Usage:
    from picker_seed_solver import find_seeds, simulate
    pool = [pool_items_from_frida]
    target = {wanted_id_1, wanted_id_2, wanted_id_3}
    seeds = find_seeds(pool, num_picks=3, target=target)
"""

from __future__ import annotations

import sys
from typing import Iterable, Sequence

PCG_MUL_1 = 0x2C9277B5
PCG_ADD_1 = 0xAC564B05
PCG_MUL_2 = 0x108EF2D9
MASK32 = 0xFFFFFFFF
MASK31 = 0x7FFFFFFF


def pcg_step(state: int) -> int:
    """Advance the PCG state and return the new (already-masked) state.

    The new state is also the value used for the next `draw % pool_size`.
    """
    s = (state * PCG_MUL_1 + PCG_ADD_1) & MASK32
    shift = ((s >> 28) + 4) & 0x1F
    s = ((s >> shift) ^ s) & MASK32
    s = (s * PCG_MUL_2) & MASK32
    s = ((s >> 22) ^ s) & MASK31
    return s


def simulate(
    seed: int, pool: Sequence[int], num_picks: int
) -> tuple[list[int], int]:
    """Run num_picks selection draws starting from `seed`.

    Returns (picked_ids, final_state). pool order matters — pass the SAME
    order the engine sees at picker entry.
    """
    state = seed & MASK31
    work = list(pool)
    n = len(work)
    out: list[int] = []
    picks_left = min(num_picks, n)
    for _ in range(picks_left):
        state = pcg_step(state)
        idx = state % n
        out.append(work[idx])
        if idx != n - 1:
            work[idx], work[n - 1] = work[n - 1], work[idx]
        n -= 1
    return out, state


def find_seeds(
    pool: Sequence[int],
    num_picks: int,
    target: set[int],
    *,
    seed_range: Iterable[int] | None = None,
    limit: int = 1,
    progress_every: int = 0x1000000,
) -> list[int]:
    """Brute-force seeds whose simulated output set equals `target`.

    With ordered targets, build a list[int] target and compare lists; here
    we compare as a set so order-independent matches are reported.

    seed_range: iterable of seeds to test. Default: 0..2**31-1 (full space).
    limit: stop after this many matches (default 1).
    """
    if len(target) != num_picks:
        raise ValueError(
            f"target size ({len(target)}) must equal num_picks ({num_picks})"
        )
    if seed_range is None:
        seed_range = range(MASK31 + 1)

    matches: list[int] = []
    for i, seed in enumerate(seed_range):
        out, _ = simulate(seed, pool, num_picks)
        if set(out) == target:
            matches.append(seed)
            if len(matches) >= limit:
                break
        if progress_every and (i + 1) % progress_every == 0:
            print(f"  progress: {i+1:>10} seeds tested, "
                  f"{len(matches)} match(es)", file=sys.stderr)
    return matches


# --- self-test (synthetic) ----------------------------------------------------

if __name__ == "__main__":
    # Synthetic round-trip: pick a seed, simulate, then verify find_seeds
    # rediscovers it on a small pool.
    pool = list(range(20))
    seed_known = 0xDEADBEEF & MASK31
    expected, _ = simulate(seed_known, pool, num_picks=3)
    print(f"known seed 0x{seed_known:08x} -> picks {expected}")

    found = find_seeds(
        pool,
        num_picks=3,
        target=set(expected),
        seed_range=range(0xDEAD0000, 0xDEAE0000),
        limit=5,
    )
    print(f"matches in 0xDEAD0000..0xDEAE0000: "
          f"{[hex(s) for s in found]}")

    # Verify each match reproduces the target:
    for s in found:
        out, _ = simulate(s, pool, num_picks=3)
        assert set(out) == set(expected), f"seed 0x{s:x} failed re-simulation"
    print("self-test ok")
