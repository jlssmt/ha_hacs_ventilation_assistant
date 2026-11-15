"""Constants for Ventilation Assistant."""

from __future__ import annotations

from enum import StrEnum

DOMAIN = "ventilation_assistant"

PLATFORMS = ["sensor", "binary_sensor", "number", "select"]

DATA_GLOBAL_OPTIONS = "global_options"

CONF_KIND = "kind"
CONF_GLOBAL = "global"
CONF_DEVICE = "device"

GLOBAL_OUTDOOR_DEVICE_ID = "ventilation_assistant_global"
GLOBAL_OUTDOOR_TEMP_ENTITY_ID = (
    "sensor.ventilation_assistant_global_outdoor_temperature"
)
GLOBAL_OUTDOOR_HUMIDITY_ENTITY_ID = (
    "sensor.ventilation_assistant_global_outdoor_humidity"
)
GLOBAL_OUTDOOR_ABSOLUTE_HUMIDITY_ENTITY_ID = (
    "sensor.ventilation_assistant_global_absolute_outdoor_humidity"
)
GLOBAL_OUTDOOR_CO2_ENTITY_ID = (
    "sensor.ventilation_assistant_global_outdoor_carbon_dioxide"
)

CONF_INDOOR_TEMP_ENTITIES = "indoor_temp_entities"
CONF_INDOOR_HUMIDITY_ENTITIES = "indoor_humidity_entities"
CONF_INDOOR_CO2_ENTITIES = "indoor_co2_entities"
CONF_OUTDOOR_TEMP_ENTITIES = "outdoor_temp_entities"
CONF_OUTDOOR_HUMIDITY_ENTITIES = "outdoor_humidity_entities"
CONF_OUTDOOR_CO2_ENTITIES = "outdoor_co2_entities"
CONF_DOOR_WINDOW_ENTITIES = "door_window_entities"

CONF_COMFORT_TEMP_MIN = "comfort_temp_min"
CONF_COMFORT_TEMP_MAX = "comfort_temp_max"
CONF_COMFORT_RH_MIN = "comfort_rh_min"
CONF_COMFORT_RH_MAX = "comfort_rh_max"
CONF_COMFORT_CO2_MAX = "comfort_co2_max"
CONF_PRIORITY = "priority"
CONF_CO2_TARGET = "co2_target"
CONF_MIN_AIRING_MINUTES = "min_airing_minutes"

DEFAULT_COMFORT_TEMP_MIN = 19.0
DEFAULT_COMFORT_TEMP_MAX = 24.0
DEFAULT_COMFORT_RH_MIN = 40.0
DEFAULT_COMFORT_RH_MAX = 60.0
DEFAULT_COMFORT_CO2_MAX = 2000.0
DEFAULT_CO2_TARGET = 500.0
DEFAULT_MIN_AIRING_MINUTES = 5.0
DEFAULT_OUTDOOR_CO2 = 400

# A value counts as flat when it fell by less than the flat limit over the trend
# window. Sensors lag behind the airing, so nothing counts as ventilated enough
# before the window was open for the configured minimum airing time.
CO2_TREND_WINDOW_SECONDS = 30.0
RH_TREND_WINDOW_SECONDS = 60.0
CO2_FLAT_PPM = 10.0
RH_FLAT_PERCENT = 1.0


class Priority(StrEnum):
    """Ventilation advice priority."""

    TEMPERATURE = "temperature"
    HUMIDITY = "humidity"
    CO2 = "carbon_dioxide"


class Advice(StrEnum):
    """Ventilation advice."""

    KEEP_CLOSED = "keep_closed"
    OPEN = "open"
    KEEP_OPEN = "keep_open"
    CLOSE = "close"
