# Automated Puzzle Generation

Design for a fully automated, end-to-end puzzle generation pipeline that produces Cutline's daily grid puzzles from the Lahman database, with quality guardrails that refuse to publish low-quality grids.

## Goals

- Produce 7 days of published puzzles (2026-04-15 through 2026-04-21) as the immediate deliverable.
- Do it via a repeatable pipeline that can be re-run to generate future days (automation, not a one-off).
- Automatically pick the category, pick qualifiers and imposters, and publish — no human step in the loop.
- Guardrails refuse to publish if the grid would be low quality; the generator falls back to the next category.
- Grids are recognizable to modern fans: no obscure 19th-century players, imposters are plausible near-misses.

## Non-goals

- No hand-curated puzzles. If automation can't produce a viable grid for a date, it errors loudly; a human doesn't step in.
- No admin UI changes. The generator is a CLI. A future scheduled job can wrap it.
- No player photo sourcing. If `photo_url` is NULL it stays NULL.
- No new intersection categories (e.g. "30+ HR as a Yankee"). Stays behind a future expansion.

## High-level architecture

Three units, each independently testable:

1. **Ingest extension** — `scripts/ingest_lahman.py` gains loaders for `AwardsSharePlayers.csv` and `AwardsShareManagers.csv`, populating `Award` rows with `notes="top_3"` / `"top_5"` for non-winning vote recipients. This feeds the existing `_award_near_misses` imposter query.
2. **Category catalog** — `app/categories.py` gains a `_stat_category` factory and 9 new stat-milestone entries in `REGISTRY`. The `Category` interface is unchanged; new categories satisfy the same `qualifier_fn` / `imposter_fn` contract.
3. **Generator** — new `scripts/generate_puzzles.py` picks a category for a date, samples 6 qualifiers + 3 imposters with date-seeded weighted sampling, writes a `Puzzle` + 9 `PuzzleEntry` rows, published=True.

Data flow:

```
Lahman CSV ─► ingest_lahman ─► players / awards / season_stats / all_star_appearances
                                               │
                                               ▼
                            categories.REGISTRY.qualifier_fn / imposter_fn
                                               │
                                               ▼
                            generate_puzzles ─► Puzzle + PuzzleEntry (published)
```

## Ingest additions

Add two new loaders to `ingest_lahman.py`, called after `_load_awards`:

- `_load_award_shares(session, opener, id_map)` reads `AwardsSharePlayers.csv`. For each row, map `awardID` → internal `award_type` via the existing `AWARD_NAME_MAP`. Skip the row if an `Award` already exists for `(player_id, award_type, year)` with `notes="winner"`. Otherwise insert an `Award` row with:
  - `notes="top_3"` if `pointsWon / pointsMax >= 0.40`
  - `notes="top_5"` otherwise
  - Only insert rows where `pointsWon > 0` (i.e. they actually received a vote).
- `_load_award_share_managers(session, opener, id_map)` same idea for `AwardsShareManagers.csv`.

This is idempotent: the `(player_id, award_type, year)` uniqueness check prevents re-insertion, and re-running Lahman ingest after already loading winners simply adds the non-winner rows.

**Why**: the existing `_award_near_misses` query in `categories.py` pulls `Award` rows with `notes IS NOT NULL` as imposter candidates. Wiring share data in populates that query automatically, so award categories get real voting-based imposter pools with no downstream code change.

## Category catalog

### Existing (unchanged)

The 9 award categories in `REGISTRY` stay as-is. With share-vote data ingested, their imposter pools go from ~0 to hundreds of real near-misses.

### New stat-milestone categories

Add a `_stat_category` factory that takes qualifier and imposter SQL predicates (both over `season_stats` and/or `all_star_appearances`) and produces a `Category`. Register 9 new entries:

| Key | Display | Qualifier | Imposter |
|---|---|---|---|
| `stat_500_hr` | Hit 500+ career HR | `SUM(home_runs) ≥ 500` | `SUM(home_runs) BETWEEN 400 AND 499` |
| `stat_3000_hits` | 3,000+ career hits | `SUM(hits) ≥ 3000` | `SUM(hits) BETWEEN 2500 AND 2999` |
| `stat_300_wins` | 300+ career wins | `SUM(wins) ≥ 300` | `SUM(wins) BETWEEN 240 AND 299` |
| `stat_3000_k` | 3,000+ career strikeouts (P) | `SUM(strikeouts) ≥ 3000` (pitcher) | `SUM(strikeouts) BETWEEN 2500 AND 2999` |
| `stat_400_sb` | 400+ career stolen bases | `SUM(stolen_bases) ≥ 400` | `SUM(stolen_bases) BETWEEN 300 AND 399` |
| `stat_50_hr_season` | Hit 50+ HR in a season | `MAX(home_runs) ≥ 50` | `MAX(home_runs) BETWEEN 45 AND 49` |
| `stat_350_avg_season` | Hit .350+ in a qualified season | any season with `batting_avg ≥ 0.350 AND games ≥ 100` | best qualifying season in `[0.330, 0.350)` and never a .350 |
| `stat_40_40` | Had a 40/40 season | season with `home_runs ≥ 40 AND stolen_bases ≥ 40` | season with `home_runs ≥ 35 AND stolen_bases ≥ 35` but never a 40/40 |
| `stat_10_allstar` | Made 10+ All-Star Games | `COUNT(all_star_appearances) ≥ 10` | `COUNT(all_star_appearances) BETWEEN 7 AND 9` |

Notes on implementation:

- "3,000+ career strikeouts (P)" uses a pitcher floor (e.g. `SUM(innings_pitched) ≥ 500`) to exclude the handful of two-way players whose batting strikeouts get summed into `strikeouts` — actually, `SeasonStat.strikeouts` is populated from the pitching CSV in the existing ingest (line `_load_pitching` sets `season.strikeouts = _int(row.get("SO"))`), so pitchers are the only ones with values there. No pitcher-floor needed; document this dependency in a comment.
- `batting_avg ≥ .350 qualified` uses `games ≥ 100` as a rough proxy for a full-season qualifier — Lahman's per-season `G` isn't a PA-weighted qualifier but it's close enough for puzzle purposes.
- All qualifier/imposter results go through the **All-Star gate** (`≥ 1 all_star_appearances` row) before the generator sees them. This happens in the generator, not in each category, so categories stay lean.

## Generator algorithm

`scripts/generate_puzzles.py`:

```python
def generate_for_date(session, target_date: date) -> Puzzle | None:
    if puzzle_already_exists(session, target_date):
        return None  # idempotent skip

    rng = random.Random(seed=int(target_date.strftime("%Y%m%d")))
    recent_keys = recently_used_categories(session, target_date, days=14)
    candidate_keys = [k for k in REGISTRY if k not in recent_keys]
    rng.shuffle(candidate_keys)

    for key in candidate_keys:
        category = REGISTRY[key]
        qualifiers = await allstar_gate(session, await category.qualifier_fn(session))
        imposters  = await allstar_gate(session, await category.imposter_fn(session))
        imposters  = [p for p in imposters if p not in qualifiers]  # no overlap

        if len(qualifiers) < 6 or len(imposters) < 3:
            continue

        picks_q = weighted_sample(qualifiers, 6, weights=allstar_counts(qualifiers), rng=rng)
        picks_i = weighted_sample(imposters,  3, weights=allstar_counts(imposters),  rng=rng)
        grid = list(zip(range(9), rng.sample(picks_q + picks_i, 9)))

        return write_puzzle(session, target_date, category, grid, picks_q)

    raise GeneratorError(f"no viable category for {target_date}")
```

**Key details:**

- **Seeded RNG**: `int(target_date.strftime("%Y%m%d"))` as seed — re-running the generator for the same date produces the same puzzle (idempotency for humans + reproducibility).
- **Weighted sampling**: weight = `all_star_appearance_count + 1` (the `+1` avoids zero-weight for any player with at least one AS game; all gated players have ≥1, so this is functionally `all_star_count`). Implemented via `random.Random.choices` with replacement filtered for duplicates, or `numpy`-free reservoir sampling if a hand-rolled implementation is preferred.
- **Grid shuffle**: the 9 picks are shuffled into `grid_position` 0–8 so `is_qualifier` doesn't correlate with position.
- **Explanations**: auto-generated per entry from the source Award / SeasonStat rows, e.g. `"Won NL MVP in 2022 with STL."` for awards, `"Career 523 HR."` for stat milestones. Template strings per category key.

**Guardrails (refuse-to-publish):**

1. Pool too thin: `len(qualifiers) < 6` OR `len(imposters) < 3` → skip category.
2. Category used within last 14 days → skip.
3. Qualifier and imposter pools overlap (defensive, should never happen) → skip.
4. If all categories skipped → `GeneratorError`. Exits non-zero; no puzzle written.

## CLI

```
python -m scripts.generate_puzzles --days 7                   # 7 consecutive starting tomorrow
python -m scripts.generate_puzzles --start 2026-04-15 --days 7
python -m scripts.generate_puzzles --date 2026-04-15          # single day
python -m scripts.generate_puzzles --days 7 --dry-run         # print grids, don't write
```

- `--dry-run` prints the category, the 9 picks, and the explanations, then rolls back.
- Exit code 0 on full success, 1 on any `GeneratorError` (other days before the failure still written unless `--all-or-nothing` is passed — out of scope for v1, default is "stop at first failure").
- Idempotent: if a puzzle already exists for a given date, that date is skipped with a log line.

## Testing

- `tests/test_categories_stat.py` — unit-test each new stat category's SQL against a fixture DB with a handful of known players (e.g., Bonds qualifies for `stat_500_hr`, Andre Dawson sits in the 400–499 imposter band).
- `tests/test_generator.py` — integration test: seed a fixture DB, run the generator for a date, assert a `Puzzle` + 9 `PuzzleEntry` rows exist, assert 6 qualifiers + 3 imposters, assert category variety across 7 consecutive dates (no dup within 14 days).
- `tests/test_generator_guardrails.py` — fixture with too-thin pools for most categories; assert the generator falls back to a viable one.
- `tests/test_ingest_shares.py` — load a synthetic AwardsSharePlayers.csv, assert the expected imposter `Award` rows land with correct `notes`.

All tests reuse the existing file-backed SQLite fixture (`tests/conftest.py`).

## Rollout

1. Run `python -m scripts.ingest_lahman --zip /mnt/c/Users/noahb/Downloads/lahman_1871-2025_csv.zip` on the local dev DB. (Production already has Lahman, but the share-vote extension needs a re-run with the updated script.)
2. `python -m scripts.generate_puzzles --start 2026-04-15 --days 7 --dry-run` — sanity check the 7 grids before shipping.
3. Drop `--dry-run`, run for real. 7 published puzzles now live.
4. Future: wrap in a scheduled job (cron / systemd timer / GitHub Action) that runs nightly with `--days 1 --start $(date -d tomorrow +%Y-%m-%d)` to keep the pipeline topped up.

## Open questions (resolved — for context)

- *Fame filter*: All-Star gate (≥1 AS appearance). Decided.
- *Category variety*: awards + 9 stat-milestone categories. Decided.
- *Automation level*: end-to-end with guardrails; no human review step. Decided.
- *Sampling*: date-seeded weighted sampling with All-Star count as weight. Decided.
