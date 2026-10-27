"""Read-only guard after a 50 MHz overlay download. DOES NOT set any clock.
The .hwh must be checked on the host BEFORE download; this is a second guard.
Do not use for the trusted C7 overlay, which retains its original clock contract.
"""
from __future__ import annotations
import math

TARGET_MHZ = 50.0
STA_PERIOD_NS = 20.0

def require_refinement_clock(clocks, clock_dict):
    item = clock_dict.get(0, clock_dict.get('0'))
    if not isinstance(item, dict):
        raise RuntimeError('FCLK0_METADATA_MISSING')
    if not bool(item.get('enable')):
        raise RuntimeError('FCLK0_METADATA_DISABLED')
    try:
        div0, div1 = int(item['divisor0']), int(item['divisor1'])
    except (KeyError, ValueError, TypeError) as exc:
        raise RuntimeError('FCLK0_DIVIDERS_MISSING') from exc
    if not (1 <= div0 <= 63 and 1 <= div1 <= 63 and div0 * div1 == 20):
        raise RuntimeError('FCLK0_WRONG_DIVIDERS: expected IO_PLL /20 total')
    actual = float(clocks.fclk0_mhz)  # register-derived readback, not a pin measurement
    if not math.isfinite(actual) or not 49.9 <= actual <= 50.000001:
        raise RuntimeError(f'FCLK0_MISMATCH actual={actual}; STA=20ns')
    return {'actual_register_derived_mhz': actual,
            'metadata_divisor0': div0, 'metadata_divisor1': div1,
            'sta_period_ns': STA_PERIOD_NS, 'set_clock_performed': False}
