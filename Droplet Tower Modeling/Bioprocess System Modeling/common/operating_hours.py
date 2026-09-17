"""Effective operating-hours derivation for all four SCP routes.

Two non-overlapping downtime sources, derived from first principles rather
than a generic "350 days/yr" default (Framework §5a):

  - Plant-wide turnaround: all lines down simultaneously, 2 wk/yr = 336 h/yr.
  - Per-line contamination restart: 2 restarts/yr at 336 h each = 672 h/yr,
    independent/staggered across lines (Cauldron/Stansfield, AgFunderNews
    March 2024 — 6-month campaign as stated margin below 8-month achieved).

Effective per-line operating hours: 8,760 − 336 − 672 = 7,752 h/yr (88.5 %).

CONTAMINATION_RESTART_H is imported by common/seed_train.py.
Framework §5a / Spec §common/operating_hours.py.
"""

CALENDAR_HOURS:        int   = 8_760   # h/yr
PLANT_TURNAROUND_H:    int   = 336     # 2 wk/yr, all lines simultaneously — Framework §5a
RESTARTS_PER_YEAR:     int   = 2       # 6-month campaigns — Framework §5a / §9.2
RESTART_DURATION_H:    int   = 336     # h per restart event — Framework §5a
CONTAMINATION_RESTART_H: int = RESTARTS_PER_YEAR * RESTART_DURATION_H  # = 672 h/yr per line


def effective_operating_hours() -> float:
    """Return effective per-line operating hours per year.

    8,760 − 336 (turnaround) − 672 (contamination restarts) = 7,752 h/yr.
    Used by common/kinetics.py (throughput sizing) and common/economics.py
    (operating_days argument to SCPTEA).  Framework §5a.
    """
    return float(CALENDAR_HOURS - PLANT_TURNAROUND_H - CONTAMINATION_RESTART_H)
