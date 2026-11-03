"""Holdout sizing: minimum detectable effect (MDE) for a randomised holdout test.

Two-sided test, normal approximation:
    MDE = (z_(1 - alpha/2) + z_power) * SE
    SE  = sqrt(p (1 - p) (1/n_t + 1/n_c))      for a repurchase rate p
    SE  = sd * sqrt(1/n_t + 1/n_c)              for revenue per customer
"""

from __future__ import annotations

import math

from scipy.stats import norm


def z_total(alpha: float = 0.05, power: float = 0.80) -> float:
    return float(norm.ppf(1 - alpha / 2) + norm.ppf(power))


def mde_rate(p0: float, n_treat: float, n_control: float, alpha: float = 0.05, power: float = 0.80) -> float:
    """Smallest absolute lift in a rate (e.g. 0.012 = +1.2 pp) the test can reliably detect."""
    if n_treat <= 0 or n_control <= 0:
        return float("inf")
    return z_total(alpha, power) * math.sqrt(p0 * (1 - p0) * (1 / n_treat + 1 / n_control))


def mde_mean(sd: float, n_treat: float, n_control: float, alpha: float = 0.05, power: float = 0.80) -> float:
    """Smallest absolute lift in a mean (e.g. revenue per customer in CU) the test can detect."""
    if n_treat <= 0 or n_control <= 0:
        return float("inf")
    return z_total(alpha, power) * sd * math.sqrt(1 / n_treat + 1 / n_control)


def holdout_needed_for_rate(p0: float, n_total: float, target_mde: float, alpha: float = 0.05,
                            power: float = 0.80) -> float | None:
    """Smallest holdout share (0-0.5) that detects `target_mde`; None if even 50/50 is not enough."""
    lo, hi = 0.001, 0.5
    if mde_rate(p0, n_total * (1 - hi), n_total * hi, alpha, power) > target_mde:
        return None
    for _ in range(60):
        mid = (lo + hi) / 2
        if mde_rate(p0, n_total * (1 - mid), n_total * mid, alpha, power) > target_mde:
            lo = mid
        else:
            hi = mid
    return hi
