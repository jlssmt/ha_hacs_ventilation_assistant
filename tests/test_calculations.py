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


SETTINGS = ComfortSettings(19, 24, 40, 60, Priority.CO2, co2_target=500, co2_max=1000)


def _enough(**overrides: object) -> bool | None:
    values: dict[str, object] = {
        "settings": SETTINGS,
        "any_open": True,
        "open_seconds": 400.0,
        "outdoor_temp": 5.0,
        "indoor_co2": 800.0,
        "co2_flat": False,
        "indoor_rh": 50.0,
        "projected_rh": 40.0,
        "rh_flat": False,
    }
    values.update(overrides)
    return ventilated_enough(**values)  # type: ignore[arg-type]


class TrendTrackerTests(unittest.TestCase):
    def test_drop_needs_a_full_window(self) -> None:
        tracker = TrendTracker(100, 10)
        for t in range(0, 60, 10):
            tracker.add(t, 1000 - t)

        self.assertIsNone(tracker.drop(60))

    def test_drop_compares_first_and_last_third(self) -> None:
        tracker = TrendTracker(100, 10)
        for t in range(0, 101, 10):
            tracker.add(t, 1000 - t * 2)

        self.assertEqual(tracker.drop(100), 140)

    def test_flat_curve_has_no_drop(self) -> None:
        tracker = TrendTracker(100, 10)
        for t in range(0, 101, 10):
            tracker.add(t, 740 + (t % 20) / 10)

        self.assertLess(tracker.drop(100) or 0, 5)

    def test_flat_when_the_value_stopped_falling(self) -> None:
        tracker = TrendTracker(100, 10)
        for t in range(0, 201, 10):
            tracker.add(t, max(700, 1000 - t * 5))  # falls, then stays at 700

        self.assertTrue(tracker.is_flat(200))

    def test_not_flat_while_falling(self) -> None:
        tracker = TrendTracker(100, 10)
        for t in range(0, 101, 10):
            tracker.add(t, 1000 - t * 2)

        self.assertFalse(tracker.is_flat(100))

    def test_reset_forgets_samples(self) -> None:
        tracker = TrendTracker(100, 10)
        for t in range(0, 101, 10):
            tracker.add(t, 900)
        tracker.reset()

        self.assertIsNone(tracker.drop(100))


class VentilatedEnoughTests(unittest.TestCase):
    def test_not_done_while_still_falling(self) -> None:
        self.assertFalse(_enough())

    def test_done_when_co2_flat_and_humidity_flat(self) -> None:
        self.assertTrue(_enough(co2_flat=True, rh_flat=True))

    def test_done_at_co2_target_and_comfortable_humidity(self) -> None:
        self.assertTrue(_enough(indoor_co2=480.0, indoor_rh=50.0))

    def test_humidity_still_falling_blocks(self) -> None:
        self.assertFalse(_enough(co2_flat=True, indoor_rh=70.0))

    def test_wet_outdoor_air_does_not_block(self) -> None:
        self.assertTrue(_enough(co2_flat=True, indoor_rh=70.0, projected_rh=80.0))

    def test_not_done_before_the_minimum_airing_time(self) -> None:
        self.assertFalse(_enough(open_seconds=120.0, co2_flat=True, rh_flat=True))
        self.assertFalse(_enough(open_seconds=None, co2_flat=True, rh_flat=True))

    def test_minimum_airing_time_is_configurable(self) -> None:
        short = ComfortSettings(
            19,
            24,
            40,
            60,
            Priority.CO2,
            co2_target=500,
            co2_max=1000,
            min_airing_minutes=1,
        )

        self.assertTrue(
            _enough(settings=short, open_seconds=90.0, co2_flat=True, rh_flat=True)
        )
        self.assertFalse(
            _enough(settings=short, open_seconds=30.0, co2_flat=True, rh_flat=True)
        )

    def test_closed_window_is_not_done(self) -> None:
        self.assertFalse(_enough(any_open=False, co2_flat=True))

    def test_unknown_contact_state_is_unknown(self) -> None:
        self.assertIsNone(_enough(any_open=None))

    def test_summer_is_never_done(self) -> None:
        self.assertFalse(_enough(outdoor_temp=22.0, co2_flat=True, rh_flat=True))

    def test_without_inputs_is_unknown(self) -> None:
        self.assertIsNone(_enough(indoor_co2=None, indoor_rh=None))


if __name__ == "__main__":
    unittest.main()
