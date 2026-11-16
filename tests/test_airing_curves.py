"""Replay recorded indoor CO2 curves through the real coordinator.

The curves in ``airing_curves.json`` come from one room over several days: fast
and slow airings, airings that were stopped early, curves that stalled above the
target and long airings that sit at the outdoor level. Times and values are
anonymised (relative seconds, rounded). Every curve is replayed the way Home
Assistant delivers it: a state change per sensor update, plus the coordinator's
timer every 15 seconds while the window is open.
"""

from __future__ import annotations

import itertools
import json
import types
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import patch

from test_global_outdoor import (
    _const_module,
    _load_integration_modules,
    _State,
    _States,
)

TARGET = 600
MIN_AIRING_SECONDS = 300
CURVES_FILE = Path(__file__).with_name("airing_curves.json")


@dataclass
class Replay:
    """What the sensor did while one curve played."""

    duration: int
    # (seconds, ppm at that moment, ventilated enough)
    steps: list[tuple[int, int, bool | None]] = field(default_factory=list)
    off_after_close: bool | None = None

    @property
    def states(self) -> list[bool | None]:
        return [state for _, _, state in self.steps]

    @property
    def first_on(self) -> tuple[int, int] | None:
        for seconds, ppm, state in self.steps:
            if state is True:
                return seconds, ppm
        return None

    @property
    def turned_on(self) -> bool:
        return self.first_on is not None

    @property
    def switches(self) -> int:
        """How often the state changed while the window was open."""

        states = self.states
        return sum(1 for a, b in itertools.pairwise(states) if a != b)

    @property
    def on_steps(self) -> list[tuple[int, int, bool | None]]:
        return [step for step in self.steps if step[2] is True]


def _load_curves() -> dict[str, tuple[int, list[tuple[int, int]]]]:
    raw = json.loads(CURVES_FILE.read_text(encoding="utf-8"))
    curves: dict[str, tuple[int, list[tuple[int, int]]]] = {}
    for name, text in raw.items():
        if name.startswith("_"):
            continue
        head, *pairs = text.split()
        points = [(int(a), int(b)) for a, b in (pair.split(":") for pair in pairs)]
        curves[name] = (int(head), points)
    return curves


CURVES = _load_curves()


def replay(name: str, **settings: float) -> Replay:
    duration, points = CURVES[name]
    integration, _ = _load_integration_modules()
    const = _const_module()
    states: dict[str, _State] = {
        "sensor.co2": _State(str(points[0][1]), "ppm"),
        "binary_sensor.window": _State("on"),
    }
    hass = types.SimpleNamespace(data={const.DOMAIN: {}}, states=_States(states))
    coordinator = integration.VentilationCoordinator(
        hass,
        integration.VentilationDeviceConfig(
            id="room",
            name="Room",
            options={
                const.CONF_INDOOR_CO2_ENTITIES: ["sensor.co2"],
                const.CONF_DOOR_WINDOW_ENTITIES: ["binary_sensor.window"],
                **settings,
            },
        ),
    )
    clock = [1000.0]
    timers: list[Any] = []

    def track(_hass: Any, action: Any, _interval: Any) -> Any:
        timers.append(action)
        return timers.clear

    result = Replay(duration=duration)
    event = types.SimpleNamespace(data={})
    ppm = points[0][1]

    def observe(seconds: int) -> None:
        result.steps.append((seconds, ppm, coordinator.snapshot().ventilated_enough))

    pending = iter(points[1:])
    upcoming = next(pending, None)
    with (
        patch.object(integration.time, "monotonic", lambda: clock[0]),
        patch.object(integration, "async_track_time_interval", track),
    ):
        coordinator._async_input_changed(event)  # the window opens
        observe(0)
        for tick in range(15, duration + 1, 15):
            while upcoming is not None and upcoming[0] <= tick:
                clock[0] = 1000.0 + upcoming[0]
                ppm = upcoming[1]
                states["sensor.co2"] = _State(str(ppm), "ppm")
                coordinator._async_input_changed(event)
                observe(upcoming[0])
                upcoming = next(pending, None)
            clock[0] = 1000.0 + tick
            timers[0](None)
            observe(tick)
        states["binary_sensor.window"] = _State("off")
        coordinator._async_input_changed(event)
        result.off_after_close = coordinator.snapshot().ventilated_enough
    return result


# Window closed within (or right after) the minimum airing time: the sensor
# never had a chance to report "enough".
CLOSED_EARLY = ("c03", "c11", "c13", "c14")

# Still falling at a clear rate when the window was closed: airing was still
# paying off, so the sensor must stay off.
STILL_FALLING = ("c04", "c07", "c19", "c24")

# The indoor value reached the target (or sat at the outdoor level all along).
REACHED_TARGET = (
    "c01",
    "c02",
    "c06",
    "c08",
    "c09",
    "c10",
    "c12",
    "c15",
    "c20",
    "c21",
    "c22",
    "c23",
)

# The fall stalled above the target (a plateau at 630 to 770 ppm): better to
# close the window and air again later than wait for the last few ppm.
STALLED = ("c05", "c16", "c17", "c25")

# Stalled, climbed by about 25 ppm per minute, then fell again.
CLIMBS_AGAIN = "c18"

# Sensors reporting every 10 to 15 seconds (c01-c18) and every 30 seconds
# (c19-c25) are covered by the same assertions.


class AiringCurveTests(unittest.TestCase):
    def test_every_recorded_curve_is_covered(self) -> None:
        covered = {
            *CLOSED_EARLY,
            *STILL_FALLING,
            *STALLED,
            *REACHED_TARGET,
            CLIMBS_AGAIN,
        }

        self.assertEqual(covered, set(CURVES))

    def test_never_on_before_the_minimum_airing_time(self) -> None:
        for name in CURVES:
            with self.subTest(name):
                early = [s for s in replay(name).steps if s[0] < MIN_AIRING_SECONDS]

                self.assertTrue(all(state is False for _, _, state in early))

    def test_off_once_the_window_closes(self) -> None:
        for name in CURVES:
            with self.subTest(name):
                self.assertIs(replay(name).off_after_close, False)

    def test_closing_early_never_reports_enough(self) -> None:
        for name in CLOSED_EARLY:
            with self.subTest(name):
                self.assertFalse(replay(name).turned_on)

    def test_a_fall_at_a_clear_rate_keeps_the_sensor_off(self) -> None:
        for name in STILL_FALLING:
            with self.subTest(name):
                self.assertFalse(replay(name).turned_on)

    def test_reaching_the_target_turns_the_sensor_on_and_it_stays_on(self) -> None:
        for name in REACHED_TARGET:
            with self.subTest(name):
                result = replay(name)
                first = result.first_on

                assert first is not None
                seconds, ppm = first
                self.assertGreaterEqual(seconds, MIN_AIRING_SECONDS)
                self.assertLessEqual(ppm, TARGET)
                # one switch from off to on, and no flapping afterwards, even on
                # the long plateaus at the outdoor level where the value jitters
                self.assertEqual(result.switches, 1)
                states = result.states
                self.assertTrue(all(s is True for s in states[states.index(True) :]))

    def test_a_plateau_above_the_target_ends_the_airing(self) -> None:
        for name in STALLED:
            with self.subTest(name):
                result = replay(name)
                first = result.first_on

                assert first is not None
                seconds, ppm = first
                self.assertGreaterEqual(seconds, MIN_AIRING_SECONDS)
                self.assertGreater(ppm, TARGET)
                self.assertLess(ppm, 800)
                self.assertEqual(result.switches, 1)
                states = result.states
                self.assertTrue(all(s is True for s in states[states.index(True) :]))

    def test_a_climbing_value_switches_the_sensor_off_again(self) -> None:
        # on at the plateau, off while it climbs, on again once it falls.
        result = replay(CLIMBS_AGAIN)
        first = result.first_on
        assert first is not None
        _, ppm_when_on = first
        states = result.states
        off_after_on = [
            (s, p)
            for s, p, state in result.steps
            if state is False and s > first[0] and s < result.duration
        ]

        self.assertEqual(result.switches, 3)
        self.assertTrue(off_after_on)
        self.assertGreater(off_after_on[0][1], ppm_when_on)  # the climb
        self.assertIs(states[-1], True)

    def test_no_curve_reports_enough_far_above_the_target(self) -> None:
        for name in CURVES:
            with self.subTest(name):
                self.assertTrue(all(p <= 800 for _, p, _ in replay(name).on_steps))

    def test_a_longer_extra_airing_time_waits_for_the_target(self) -> None:
        const = _const_module()
        for name in ("c05", "c17"):
            with self.subTest(name):
                patient = replay(name, **{const.CONF_MAX_EXTRA_AIRING_MINUTES: 8.0})
                default = replay(name)

                assert default.first_on is not None
                assert patient.first_on is not None
                self.assertGreater(patient.first_on[0], default.first_on[0])
                self.assertLessEqual(patient.first_on[1], TARGET)

    def test_a_longer_minimum_airing_time_delays_the_signal(self) -> None:
        const = _const_module()
        result = replay("c15", **{const.CONF_MIN_AIRING_MINUTES: 10.0})

        assert result.first_on is not None
        self.assertGreaterEqual(result.first_on[0], 600)
        self.assertTrue(
            all(s is False for t, _, s in result.steps if t < 600),
        )


if __name__ == "__main__":
    unittest.main()
