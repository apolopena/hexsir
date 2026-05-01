"""Mint a clean starting save from a chapter-boss-kill proof.

Pure transformation — no semantic knobs. Output is always a chapter-1
starting save with every per-run field zeroed and every held-inventory
field zeroed (level=1, xp=0, stars=0, feathers=0, keys=0, etc.).

The mint is a thin orchestrator over the setter functions in
`lib.setters`; both `rerw mint savefile` and `rerw write savefile <field>`
share that same library so behavior can't drift between them.
"""

from __future__ import annotations

from dataclasses import dataclass

from lib import cooked
from lib import setters


@dataclass
class MintStep:
    """One mint operation, with old/new values for verbose output."""

    label: str
    old: str
    new: str


@dataclass
class MintReport:
    steps: list[MintStep]


def mint_object_section(cf: cooked.CookedFile) -> MintReport:
    """Apply mint transformations to `cf.object_section` in place.

    Returns a MintReport with per-step old/new values for caller display.
    The caller is responsible for re-encoding the file (which auto-recomputes
    the body CRC32) and for any post-encode chapter rollback.
    """
    steps: list[MintStep] = []

    # 1. HC per-run damage stats and dream-shards-spent.
    old_dmg = setters.zero_per_run_damage(cf)
    steps.append(
        MintStep(
            label="HC per-run damage floats",
            old=", ".join(f"{v:g}" for v in old_dmg),
            new="0, 0, 0, 0",
        )
    )

    old_ds = setters.zero_dream_shards_spent(cf)
    steps.append(
        MintStep(
            label="HC dream-shards-spent (dynamic offset)",
            old=f"{old_ds:g}",
            new="0",
        )
    )

    # 2. HC post-ingredient-vector scalars.
    old_fs = setters.set_feathers_spent(cf, 0)
    steps.append(
        MintStep(label="HC feathers-spent stat", old=str(old_fs), new="0")
    )

    old_stars = setters.set_stars(cf, 0)
    steps.append(
        MintStep(label="HC stars-of-fate", old=str(old_stars), new="0")
    )

    # 3. CRP / HC held-inventory.
    old_held = setters.set_held_feathers(cf, 0)
    steps.append(
        MintStep(label="CRP held-feathers", old=str(old_held), new="0")
    )

    old_keys = setters.set_held_keys(cf, 0)
    steps.append(
        MintStep(label="HC held-keys", old=str(old_keys), new="0")
    )

    # 4. HSD score floats. Must run BEFORE remove_activity_scores.
    n_floats = setters.zero_score_floats(cf)
    steps.append(
        MintStep(
            label="HSD score floats (counts/nickname preserved)",
            old=f"{n_floats} float(s)",
            new="0",
        )
    )

    # 5. CRP playtime.
    old_pt = setters.zero_playtime(cf)
    steps.append(
        MintStep(label="CRP playtime float", old=f"{old_pt:g}", new="0")
    )

    # 6. GroupLevel.
    old_lvl = setters.set_hero_level(cf, 1)
    steps.append(MintStep(label="GroupLevel hero_level", old=str(old_lvl), new="1"))

    old_xp = setters.set_hero_xp(cf, 0)
    steps.append(MintStep(label="GroupLevel hero_xp", old=str(old_xp), new="0"))

    # 7. CRP chapter-progression end-screen banner u32.
    old_banner = setters.zero_chapter_banner(cf)
    steps.append(
        MintStep(label="CRP chapter-banner u32", old=str(old_banner), new="0")
    )

    # 8. ActivityScore removal — runs LAST.
    removed = setters.remove_activity_scores(cf)
    steps.append(
        MintStep(
            label="CRP ActivityScore records removed (count u32 -> 0)",
            old=f"{removed} record(s)",
            new="0",
        )
    )

    return MintReport(steps=steps)
