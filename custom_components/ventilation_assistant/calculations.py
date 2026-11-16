"""Pure calculation helpers for Ventilation Assistant."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from math import exp
from statistics import fmean

from .const import (
    CO2_RISE_PER_MINUTE,
    CO2_SLOW_PER_MINUTE,
    DEFAULT_CO2_TARGET,
    DEFAULT_MAX_EXTRA_AIRING_MINUTES,
    DEFAULT_MIN_AIRING_MINUTES,
    RH_RISE_PER_MINUTE,
    RH_SLOW_PER_MINUTE,
    TREND_MIN_SAMPLES,
    TREND_WINDOW_SECONDS,
    Advice,
    Priority,
)


@dataclass(frozen=True)
class ComfortSettings:
    """Comfort band and decision priority."""

    temp_min: float
    temp_max: float
    rh_min: float
    rh_max: float
    priority: Priority
    co2_max: float = 2000.0
    co2_target: float = DEFAULT_CO2_TARGET
    min_airing_minutes: float = DEFAULT_MIN_AIRING_MINUTES
    max_extra_airing_minutes: float = DEFAULT_MAX_EXTRA_AIRING_MINUTES


@dataclass(frozen=True)
class VentilationAdvice:
    """Advice split by decision input plus the priority-resolved result."""

    temperature: Advice | None
    humidity: Advice | None
    carbon_dioxide: Advice | None
    overall: Advice | None


def average(values: list[float]) -> float | None:
    """Return the arithmetic mean, or None when no usable values exist."""

    return round(fmean(values), 2) if values else None


def absolute_humidity(
    temp_c: float | None, relative_humidity: float | None
) -> float | None:
    """Calculate absolute humidity in g/m3 from temperature in C and RH in percent."""

    if temp_c is None or relative_humidity is None:
        return None
    saturation_hpa = 6.112 * exp((17.67 * temp_c) / (temp_c + 243.5))
    return round((saturation_hpa * relative_humidity * 2.1674) / (273.15 + temp_c), 2)


def relative_humidity(
    temp_c: float | None, absolute_humidity_g_m3: float | None
) -> float | None:
    """Calculate RH in percent from temperature in C and absolute humidity in g/m3."""

    if temp_c is None or absolute_humidity_g_m3 is None:
        return None
    saturation_hpa = 6.112 * exp((17.67 * temp_c) / (temp_c + 243.5))
    rh = (absolute_humidity_g_m3 * (273.15 + temp_c)) / (2.1674 * saturation_hpa)
    return round(max(0.0, min(100.0, rh)), 2)


def difference(left: float | None, right: float | None) -> float | None:
    """Return left - right, preserving unavailable inputs."""

    if left is None or right is None:
        return None
    return round(left - right, 2)


def open_ratio(open_count: int | None, total_count: int | None) -> float | None:
    """Return the percentage of open contacts."""

    if not total_count:
        return None
    if open_count is None:
        return None
    return round((open_count / total_count) * 100, 1)


def ventilation_advice(
    *,
    settings: ComfortSettings,
    any_open: bool | None,
    indoor_temp: float | None,
    outdoor_temp: float | None,
    indoor_rh: float | None,
    projected_rh: float | None,
    indoor_co2: float | None = None,
    outdoor_co2: float | None = None,
) -> Advice | None:
    """Return ventilation advice for the current measurements and contact state."""

    return ventilation_advices(
        settings=settings,
        any_open=any_open,
        indoor_temp=indoor_temp,
        outdoor_temp=outdoor_temp,
        indoor_rh=indoor_rh,
        projected_rh=projected_rh,
        indoor_co2=indoor_co2,
        outdoor_co2=outdoor_co2,
    ).overall


def ventilation_advices(
    *,
    settings: ComfortSettings,
    any_open: bool | None,
    indoor_temp: float | None,
    outdoor_temp: float | None,
    indoor_rh: float | None,
    projected_rh: float | None,
    indoor_co2: float | None = None,
    outdoor_co2: float | None = None,
) -> VentilationAdvice:
    """Return component and priority-resolved overall ventilation advice."""

    temperature_advice = _temperature_advice(
        settings, indoor_temp, outdoor_temp, indoor_rh, projected_rh
    )
    humidity_advice = _humidity_advice(
        settings, indoor_temp, outdoor_temp, indoor_rh, projected_rh
    )
    carbon_dioxide_advice = _carbon_dioxide_advice(settings, indoor_co2, outdoor_co2)

    if any_open is not None:
        temperature_advice = _apply_contact_state(temperature_advice, any_open)
        humidity_advice = _apply_contact_state(humidity_advice, any_open)
        carbon_dioxide_advice = _apply_contact_state(carbon_dioxide_advice, any_open)

    return VentilationAdvice(
        temperature=temperature_advice,
        humidity=humidity_advice,
        carbon_dioxide=carbon_dioxide_advice,
        overall=_prioritized_advice(
            settings,
            temperature_advice,
            humidity_advice,
            carbon_dioxide_advice,
        ),
    )


class TrendTracker:
    """Rolling samples of one value, collected while a window stays open."""

    def __init__(self, window: float = TREND_WINDOW_SECONDS) -> None:
        """Initialize an empty tracker."""

        self._window = window
        self._samples: deque[tuple[float, float]] = deque()

    def reset(self) -> None:
        """Forget all samples, e.g. when the window closes."""

        self._samples.clear()

    def add(self, now: float, value: float) -> None:
        """Record a sample and drop the ones older than the window."""

        self._samples.append((now, value))
        while self._samples[0][0] < now - self._window:
            self._samples.popleft()

    def slope_per_minute(self, now: float) -> float | None:
        """Return the least-squares slope over the window in units per minute.

        None until enough samples cover most of the window. A line fitted
        through all samples damps single outliers far better than comparing two
        points, and does not depend on how often the sensor reports.
        """

        samples = [(t, v) for t, v in self._samples if t >= now - self._window]
        if len(samples) < TREND_MIN_SAMPLES:
            return None
        if samples[-1][0] - samples[0][0] < 0.75 * self._window:
            return None
        mean_t = fmean(t for t, _ in samples)
        mean_v = fmean(v for _, v in samples)
        variance = sum((t - mean_t) ** 2 for t, _ in samples)
        covariance = sum((t - mean_t) * (v - mean_v) for t, v in samples)
        return covariance / variance * 60


def airing_pays_off(
    *,
    value: float,
    target: float,
    slope: float | None,
    rise: float,
    slow: float,
    max_minutes: float,
    keep_done: bool = False,
) -> bool:
    """Return whether more airing is still worth it for a value above its target.

    Airing pays off while the slope is unknown, while the value climbs again
    (airing does not keep up), or while it still falls faster than the slow
    limit. A value that falls slower, or stands still, is only worth waiting for
    when the trend reaches the target within the maximum extra airing time.
    Otherwise it is better to close the window and air again later, however far
    above the target the value is.

    With ``keep_done`` (already reported as done) only a climb counts, so a
    curve that speeds up again does not switch the signal back and forth.
    """

    if value <= target:
        return False
    if slope is None:
        return not keep_done
    if slope > rise:
        return True
    if keep_done:
        return False
    if slope < -slow:
        return True
    if slope >= 0:
        return False
    return (value - target) / -slope <= max_minutes


def ventilated_enough(
    *,
    settings: ComfortSettings,
    any_open: bool | None,
    outdoor_temp: float | None,
    indoor_co2: float | None,
    open_seconds: float | None,
    co2_slope: float | None,
    indoor_rh: float | None,
    projected_rh: float | None,
    rh_slope: float | None,
    keep_done: bool = False,
) -> bool | None:
    """Return whether more ventilation would no longer help.

    Only true once a window was open for the minimum airing time. CO2 is done at
    the target, or when it no longer falls fast and would need more than the
    maximum extra airing time to get there. Humidity is done once it is
    comfortable, cannot be improved by outdoor air, or its trend towards the
    comfort maximum is too slow. Once done it stays done until the value
    climbs. Summer (outdoor at or above the comfort temperature minimum) never
    reports done: windows stay open then.
    """

    if any_open is None:
        return None
    if (
        not any_open
        or open_seconds is None
        or open_seconds < settings.min_airing_minutes * 60
    ):
        return False
    if outdoor_temp is not None and outdoor_temp >= settings.temp_min:
        return False

    done: list[bool] = []
    if indoor_co2 is not None:
        done.append(
            not airing_pays_off(
                value=indoor_co2,
                target=settings.co2_target,
                slope=co2_slope,
                rise=CO2_RISE_PER_MINUTE,
                slow=CO2_SLOW_PER_MINUTE,
                max_minutes=settings.max_extra_airing_minutes,
                keep_done=keep_done,
            )
        )
    if indoor_rh is not None and projected_rh is not None:
        helps = (
            _humidity_advice(settings, None, None, indoor_rh, projected_rh)
            == Advice.OPEN
        )
        done.append(
            not helps
            or not airing_pays_off(
                value=indoor_rh,
                target=settings.rh_max,
                slope=rh_slope,
                rise=RH_RISE_PER_MINUTE,
                slow=RH_SLOW_PER_MINUTE,
                max_minutes=settings.max_extra_airing_minutes,
                keep_done=keep_done,
            )
        )
    return all(done) if done else None


def _apply_contact_state(advice: Advice | None, any_open: bool) -> Advice | None:
    """Translate action advice to keep-state advice when contact state is known."""

    if any_open and advice == Advice.OPEN:
        return Advice.KEEP_OPEN
    if not any_open and advice == Advice.CLOSE:
        return Advice.KEEP_CLOSED
    return advice


def _prioritized_advice(
    settings: ComfortSettings,
    temperature_advice: Advice | None,
    humidity_advice: Advice | None,
    carbon_dioxide_advice: Advice | None,
) -> Advice | None:
    ordered = {
        Priority.TEMPERATURE: (
            temperature_advice,
            humidity_advice,
            carbon_dioxide_advice,
        ),
        Priority.HUMIDITY: (
            humidity_advice,
            temperature_advice,
            carbon_dioxide_advice,
        ),
        Priority.CO2: (
            carbon_dioxide_advice,
            temperature_advice,
            humidity_advice,
        ),
    }[settings.priority]
    return next((advice for advice in ordered if advice is not None), None)


def _temperature_advice(
    settings: ComfortSettings,
    indoor_temp: float | None,
    outdoor_temp: float | None,
    indoor_rh: float | None,
    projected_rh: float | None,
) -> Advice | None:
    del indoor_rh, projected_rh
    if indoor_temp is None or outdoor_temp is None:
        return None
    if indoor_temp > settings.temp_max and outdoor_temp < indoor_temp:
        return Advice.OPEN
    if indoor_temp < settings.temp_min and outdoor_temp > indoor_temp:
        return Advice.OPEN
    return Advice.CLOSE


def _humidity_advice(
    settings: ComfortSettings,
    indoor_temp: float | None,
    outdoor_temp: float | None,
    indoor_rh: float | None,
    projected_rh: float | None,
) -> Advice | None:
    del indoor_temp, outdoor_temp
    if indoor_rh is None or projected_rh is None:
        return None
    if indoor_rh > settings.rh_max and projected_rh < indoor_rh:
        return Advice.OPEN
    if indoor_rh < settings.rh_min and projected_rh > indoor_rh:
        return Advice.OPEN
    return Advice.CLOSE


def _carbon_dioxide_advice(
    settings: ComfortSettings,
    indoor_co2: float | None,
    outdoor_co2: float | None,
) -> Advice | None:
    if indoor_co2 is None or outdoor_co2 is None:
        return None
    if indoor_co2 > settings.co2_max and outdoor_co2 < indoor_co2:
        return Advice.OPEN
    return Advice.CLOSE
