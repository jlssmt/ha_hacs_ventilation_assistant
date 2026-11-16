from __future__ import annotations

import importlib.util
import pathlib
import sys
import types
import unittest

PACKAGE = "custom_components.ventilation_assistant"
ROOT = pathlib.Path(__file__).parents[1] / "custom_components" / "ventilation_assistant"

package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT)]
sys.modules[PACKAGE] = package

for module_name in ("const", "calculations"):
    spec = importlib.util.spec_from_file_location(
        f"{PACKAGE}.{module_name}", ROOT / f"{module_name}.py"
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"{PACKAGE}.{module_name}"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)

from custom_components.ventilation_assistant.calculations import (  # noqa: E402
    ComfortSettings,
    TrendTracker,
    absolute_humidity,
    airing_pays_off,
    relative_humidity,
    ventilated_enough,
    ventilation_advice,
    ventilation_advices,
)
from custom_components.ventilation_assistant.const import Advice, Priority  # noqa: E402


class CalculationTests(unittest.TestCase):
    def test_absolute_humidity_round_trip(self) -> None:
        absolute = absolute_humidity(20.0, 50.0)

        self.assertEqual(absolute, 8.64)
        self.assertEqual(relative_humidity(20.0, absolute), 50.01)

    def test_temperature_priority_advises_open_when_cooling_helps(self) -> None:
        advice = ventilation_advice(
            settings=ComfortSettings(19, 24, 40, 60, Priority.TEMPERATURE),
            any_open=False,
            indoor_temp=26,
            outdoor_temp=18,
            indoor_rh=50,
            projected_rh=55,
        )

        self.assertEqual(advice, Advice.OPEN)

    def test_returns_temperature_humidity_and_overall_advice(self) -> None:
        advices = ventilation_advices(
            settings=ComfortSettings(19, 24, 40, 60, Priority.TEMPERATURE),
            any_open=None,
            indoor_temp=26,
            outdoor_temp=18,
            indoor_rh=70,
            projected_rh=75,
        )

        self.assertEqual(advices.temperature, Advice.OPEN)
        self.assertEqual(advices.humidity, Advice.CLOSE)
        self.assertIsNone(advices.carbon_dioxide)
        self.assertEqual(advices.overall, Advice.OPEN)

    def test_carbon_dioxide_advice_opens_when_ventilation_reduces_high_co2(
        self,
    ) -> None:
        advices = ventilation_advices(
            settings=ComfortSettings(19, 24, 40, 60, Priority.CO2, co2_max=2000),
            any_open=None,
            indoor_temp=22,
            outdoor_temp=18,
            indoor_rh=50,
            projected_rh=50,
            indoor_co2=2400,
            outdoor_co2=500,
        )

        self.assertEqual(advices.carbon_dioxide, Advice.OPEN)
        self.assertEqual(advices.overall, Advice.OPEN)

    def test_carbon_dioxide_advice_applies_contact_state(self) -> None:
        advices = ventilation_advices(
            settings=ComfortSettings(19, 24, 40, 60, Priority.CO2, co2_max=2000),
            any_open=True,
            indoor_temp=None,
            outdoor_temp=None,
            indoor_rh=None,
            projected_rh=None,
            indoor_co2=2400,
            outdoor_co2=500,
        )

        self.assertEqual(advices.carbon_dioxide, Advice.KEEP_OPEN)
        self.assertEqual(advices.overall, Advice.KEEP_OPEN)

    def test_co2_priority_falls_back_to_temperature_then_humidity(self) -> None:
        temperature_fallback = ventilation_advice(
            settings=ComfortSettings(19, 24, 40, 60, Priority.CO2),
            any_open=None,
            indoor_temp=26,
            outdoor_temp=18,
            indoor_rh=70,
            projected_rh=75,
        )
        humidity_fallback = ventilation_advice(
            settings=ComfortSettings(19, 24, 40, 60, Priority.CO2),
            any_open=None,
            indoor_temp=None,
            outdoor_temp=None,
            indoor_rh=70,
            projected_rh=55,
        )

        self.assertEqual(temperature_fallback, Advice.OPEN)
        self.assertEqual(humidity_fallback, Advice.OPEN)

    def test_temperature_and_humidity_priorities_fall_back_to_co2_last(self) -> None:
        for priority in (Priority.TEMPERATURE, Priority.HUMIDITY):
            with self.subTest(priority=priority):
                advice = ventilation_advice(
                    settings=ComfortSettings(19, 24, 40, 60, priority),
                    any_open=False,
                    indoor_temp=None,
                    outdoor_temp=None,
                    indoor_rh=None,
                    projected_rh=None,
                    indoor_co2=2400,
                    outdoor_co2=500,
                )

                self.assertEqual(advice, Advice.OPEN)

    def test_split_advices_include_contact_state_when_available(self) -> None:
        advices = ventilation_advices(
            settings=ComfortSettings(19, 24, 40, 60, Priority.HUMIDITY),
            any_open=False,
            indoor_temp=26,
            outdoor_temp=18,
            indoor_rh=70,
            projected_rh=75,
        )

        self.assertEqual(advices.temperature, Advice.OPEN)
        self.assertEqual(advices.humidity, Advice.KEEP_CLOSED)
        self.assertEqual(advices.overall, Advice.KEEP_CLOSED)

    def test_advises_open_without_contact_state_when_cooling_helps(self) -> None:
        advice = ventilation_advice(
            settings=ComfortSettings(19, 24, 40, 60, Priority.TEMPERATURE),
            any_open=None,
            indoor_temp=26,
            outdoor_temp=18,
            indoor_rh=None,
            projected_rh=None,
        )

        self.assertEqual(advice, Advice.OPEN)

    def test_advises_close_without_contact_state_when_temperature_does_not_help(
        self,
    ) -> None:
        advice = ventilation_advice(
            settings=ComfortSettings(19, 24, 40, 60, Priority.TEMPERATURE),
            any_open=None,
            indoor_temp=22,
            outdoor_temp=18,
            indoor_rh=None,
            projected_rh=None,
        )

        self.assertEqual(advice, Advice.CLOSE)

    def test_known_open_contact_changes_open_to_keep_open(self) -> None:
        advice = ventilation_advice(
            settings=ComfortSettings(19, 24, 40, 60, Priority.TEMPERATURE),
            any_open=True,
            indoor_temp=26,
            outdoor_temp=18,
            indoor_rh=None,
            projected_rh=None,
        )

        self.assertEqual(advice, Advice.KEEP_OPEN)

    def test_known_closed_contact_changes_close_to_keep_closed(self) -> None:
        advice = ventilation_advice(
            settings=ComfortSettings(19, 24, 40, 60, Priority.TEMPERATURE),
            any_open=False,
            indoor_temp=22,
            outdoor_temp=18,
            indoor_rh=None,
            projected_rh=None,
        )

        self.assertEqual(advice, Advice.KEEP_CLOSED)

    def test_temperature_priority_falls_back_to_humidity_when_temperature_missing(
        self,
    ) -> None:
        advice = ventilation_advice(
            settings=ComfortSettings(19, 24, 40, 60, Priority.TEMPERATURE),
            any_open=None,
            indoor_temp=None,
            outdoor_temp=None,
            indoor_rh=70,
            projected_rh=55,
        )

        self.assertEqual(advice, Advice.OPEN)

    def test_humidity_priority_advises_close_when_outdoor_air_worsens_humidity(
        self,
    ) -> None:
        advice = ventilation_advice(
            settings=ComfortSettings(19, 24, 40, 60, Priority.HUMIDITY),
            any_open=True,
            indoor_temp=21,
            outdoor_temp=18,
            indoor_rh=70,
            projected_rh=75,
        )

        self.assertEqual(advice, Advice.CLOSE)

    def test_humidity_priority_falls_back_to_temperature_when_humidity_missing(
        self,
    ) -> None:
        advice = ventilation_advice(
            settings=ComfortSettings(19, 24, 40, 60, Priority.HUMIDITY),
            any_open=None,
            indoor_temp=26,
            outdoor_temp=18,
            indoor_rh=None,
            projected_rh=None,
        )

        self.assertEqual(advice, Advice.OPEN)

    def test_advice_unavailable_when_no_temperature_or_humidity_advice_exists(
        self,
    ) -> None:
        advice = ventilation_advice(
            settings=ComfortSettings(19, 24, 40, 60, Priority.HUMIDITY),
            any_open=False,
            indoor_temp=None,
            outdoor_temp=None,
            indoor_rh=None,
            projected_rh=None,
        )

        self.assertIsNone(advice)


SETTINGS = ComfortSettings(
    19,
    24,
    40,
    60,
    Priority.CO2,
    co2_target=600,
    co2_max=1000,
    min_airing_minutes=5,
    max_extra_airing_minutes=5,
)


def _enough(**overrides: object) -> bool | None:
    values: dict[str, object] = {
        "settings": SETTINGS,
        "any_open": True,
        "open_seconds": 400.0,
        "outdoor_temp": 5.0,
        "indoor_co2": 800.0,
        "co2_slope": -40.0,
        "indoor_rh": 50.0,
        "projected_rh": 40.0,
        "rh_slope": -1.0,
    }
    values.update(overrides)
    return ventilated_enough(**values)  # type: ignore[arg-type]


def _tracker(values: list[float], step: float = 15.0) -> tuple[TrendTracker, float]:
    tracker = TrendTracker(120)
    now = 0.0
    for value in values:
        tracker.add(now, value)
        now += step
    return tracker, now - step


class TrendTrackerTests(unittest.TestCase):
    def test_slope_of_a_falling_line(self) -> None:
        tracker, now = _tracker([1000 - 5 * i for i in range(9)])  # -20 per minute

        self.assertAlmostEqual(tracker.slope_per_minute(now) or 0, -20, places=6)

    def test_slope_needs_enough_samples_covering_the_window(self) -> None:
        tracker, now = _tracker([1000, 990, 980])

        self.assertIsNone(tracker.slope_per_minute(now))

        tracker, now = _tracker([1000, 990, 980, 970, 960], step=10)
        self.assertIsNone(tracker.slope_per_minute(now))

    def test_slope_of_a_flat_curve_is_zero(self) -> None:
        tracker, now = _tracker([650.0] * 9)

        self.assertEqual(tracker.slope_per_minute(now), 0)

    def test_slope_ignores_a_single_outlier(self) -> None:
        tracker, now = _tracker([650, 650, 650, 650, 662, 650, 650, 650, 650])

        self.assertLess(abs(tracker.slope_per_minute(now) or 0), 1)

    def test_slope_is_positive_when_the_value_climbs_back_up(self) -> None:
        tracker, now = _tracker([600 + 5 * i for i in range(9)])

        self.assertGreater(tracker.slope_per_minute(now) or 0, 15)

    def test_old_samples_leave_the_window(self) -> None:
        tracker, now = _tracker([1000 - 40 * i for i in range(8)] + [700.0] * 12)

        self.assertEqual(tracker.slope_per_minute(now), 0)

    def test_reset_forgets_samples(self) -> None:
        tracker, now = _tracker([900.0] * 9)
        tracker.reset()

        self.assertIsNone(tracker.slope_per_minute(now))


class AiringPaysOffTests(unittest.TestCase):
    def _pays_off(
        self, value: float, slope: float | None, keep_done: bool = False
    ) -> bool:
        return airing_pays_off(
            value=value,
            target=600,
            slope=slope,
            rise=10,
            slow=20,
            max_minutes=2,
            keep_done=keep_done,
        )

    def test_never_at_or_below_the_target(self) -> None:
        self.assertFalse(self._pays_off(600, -50))
        self.assertFalse(self._pays_off(480, 20))

    def test_keeps_airing_while_the_value_still_falls_clearly(self) -> None:
        self.assertTrue(self._pays_off(900, -40))
        self.assertTrue(self._pays_off(1500, -25))
        self.assertTrue(self._pays_off(660, -25))

    def test_a_slow_fall_is_only_worth_it_close_to_the_target(self) -> None:
        self.assertTrue(self._pays_off(625, -15))  # 1.7 min
        self.assertFalse(self._pays_off(640, -15))  # 2.7 min
        self.assertFalse(self._pays_off(660, -13))  # 4.6 min

    def test_a_slow_fall_far_above_the_target_ends_the_airing(self) -> None:
        self.assertFalse(self._pays_off(900, -15))
        self.assertFalse(self._pays_off(900, -3))

    def test_a_stalled_value_ends_the_airing(self) -> None:
        self.assertFalse(self._pays_off(900, 0))
        self.assertFalse(self._pays_off(660, 3))  # breathing noise

    def test_a_clear_climb_keeps_airing(self) -> None:
        self.assertTrue(self._pays_off(660, 12))
        self.assertTrue(self._pays_off(900, 12))

    def test_unknown_slope_keeps_airing(self) -> None:
        self.assertTrue(self._pays_off(660, None))
        self.assertTrue(self._pays_off(900, None))

    def test_once_done_only_a_climb_or_the_target_matters(self) -> None:
        self.assertFalse(self._pays_off(700, -200, keep_done=True))
        self.assertFalse(self._pays_off(700, None, keep_done=True))
        self.assertTrue(self._pays_off(700, 12, keep_done=True))


class VentilatedEnoughTests(unittest.TestCase):
    def test_not_done_while_still_falling_fast(self) -> None:
        self.assertFalse(_enough())

    def test_done_at_the_co2_target_and_comfortable_humidity(self) -> None:
        self.assertTrue(_enough(indoor_co2=590.0, indoor_rh=50.0))

    def test_done_when_co2_stalls_close_to_the_target(self) -> None:
        self.assertTrue(_enough(indoor_co2=660.0, co2_slope=-2.0, rh_slope=-1.0))

    def test_done_when_co2_stalled_far_above_the_target(self) -> None:
        self.assertTrue(_enough(indoor_co2=900.0, co2_slope=0.0))

    def test_not_done_far_above_the_target_while_it_falls_steeply(self) -> None:
        self.assertFalse(_enough(indoor_co2=900.0, co2_slope=-150.0))

    def test_done_when_the_fall_is_too_slow_to_reach_the_target_in_time(self) -> None:
        self.assertTrue(_enough(indoor_co2=900.0, co2_slope=-15.0))

    def test_not_done_while_it_still_falls_at_a_clear_rate(self) -> None:
        self.assertFalse(_enough(indoor_co2=900.0, co2_slope=-30.0))

    def test_once_done_a_steeper_fall_does_not_switch_it_off(self) -> None:
        self.assertTrue(_enough(indoor_co2=700.0, co2_slope=-5.0))
        self.assertTrue(_enough(indoor_co2=700.0, co2_slope=-150.0, keep_done=True))
        self.assertFalse(_enough(indoor_co2=700.0, co2_slope=15.0, keep_done=True))

    def test_not_done_when_co2_climbs_again(self) -> None:
        self.assertFalse(_enough(indoor_co2=660.0, co2_slope=15.0))

    def test_humidity_still_falling_blocks(self) -> None:
        self.assertFalse(_enough(indoor_co2=590.0, indoor_rh=63.0, rh_slope=-1.0))

    def test_humidity_that_stalls_close_to_the_comfort_maximum_is_done(self) -> None:
        self.assertTrue(_enough(indoor_co2=590.0, indoor_rh=63.0, rh_slope=-0.05))

    def test_wet_outdoor_air_does_not_block(self) -> None:
        self.assertTrue(_enough(indoor_co2=590.0, indoor_rh=70.0, projected_rh=80.0))

    def test_not_done_before_the_minimum_airing_time(self) -> None:
        self.assertFalse(_enough(open_seconds=120.0, indoor_co2=590.0))
        self.assertFalse(_enough(open_seconds=None, indoor_co2=590.0))

    def test_minimum_airing_time_is_configurable(self) -> None:
        short = ComfortSettings(
            19,
            24,
            40,
            60,
            Priority.CO2,
            co2_target=600,
            co2_max=1000,
            min_airing_minutes=1,
        )

        self.assertTrue(_enough(settings=short, open_seconds=90.0, indoor_co2=590.0))
        self.assertFalse(_enough(settings=short, open_seconds=30.0, indoor_co2=590.0))

    def test_max_extra_airing_time_is_configurable(self) -> None:
        patient = ComfortSettings(
            19,
            24,
            40,
            60,
            Priority.CO2,
            co2_target=600,
            co2_max=1000,
            max_extra_airing_minutes=15,
        )

        self.assertTrue(_enough(indoor_co2=660.0, co2_slope=-8.0))
        self.assertFalse(
            _enough(settings=patient, indoor_co2=660.0, co2_slope=-8.0)
        )  # 7.5 min <= 15 min

    def test_closed_window_is_not_done(self) -> None:
        self.assertFalse(_enough(any_open=False, indoor_co2=590.0))

    def test_unknown_contact_state_is_unknown(self) -> None:
        self.assertIsNone(_enough(any_open=None))

    def test_summer_is_never_done(self) -> None:
        self.assertFalse(_enough(outdoor_temp=22.0, indoor_co2=590.0))

    def test_without_inputs_is_unknown(self) -> None:
        self.assertIsNone(_enough(indoor_co2=None, indoor_rh=None))


if __name__ == "__main__":
    unittest.main()
