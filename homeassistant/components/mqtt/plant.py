"""Camera that loads a picture from an MQTT topic."""
import logging

import voluptuous as vol

from homeassistant.components import mqtt, plant
from homeassistant.components.plant import (
    CONF_SENSOR_BATTERY_LEVEL,
    CONF_SENSOR_BRIGHTNESS,
    CONF_SENSOR_CONDUCTIVITY,
    CONF_SENSOR_MOISTURE,
    CONF_SENSOR_TEMPERATURE,
    Plant,
)
from homeassistant.const import CONF_DEVICE, CONF_NAME, CONF_SENSORS, CONF_UNIQUE_ID
from homeassistant.helpers import config_validation as cv, entity_registry
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.reload import async_setup_reload_service
from homeassistant.helpers.typing import ConfigType, HomeAssistantType

from . import (
    ATTR_DISCOVERY_HASH,
    DOMAIN,
    PLATFORMS,
    MqttAttributes,
    MqttAvailability,
    MqttDiscoveryUpdate,
    MqttEntityDeviceInfo,
)
from .discovery import MQTT_DISCOVERY_NEW, clear_discovery_hash

_LOGGER = logging.getLogger(__name__)

CONF_TOPIC = "topic"
DEFAULT_NAME = "MQTT Plant"

SCHEMA_SENSORS = vol.Schema(
    {
        vol.Optional(CONF_SENSOR_BATTERY_LEVEL): cv.string,
        vol.Optional(CONF_SENSOR_MOISTURE): cv.string,
        vol.Optional(CONF_SENSOR_CONDUCTIVITY): cv.string,
        vol.Optional(CONF_SENSOR_TEMPERATURE): cv.string,
        vol.Optional(CONF_SENSOR_BRIGHTNESS): cv.string,
        vol.Optional("timestamp"): cv.string,
    }
)

PLATFORM_SCHEMA = (
    mqtt.MQTT_BASE_PLATFORM_SCHEMA.extend(
        {
            vol.Optional(CONF_DEVICE): mqtt.MQTT_ENTITY_DEVICE_INFO_SCHEMA,
            vol.Optional(CONF_SENSORS): SCHEMA_SENSORS,
            vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
            vol.Optional(CONF_UNIQUE_ID): cv.string,
            vol.Optional("device_class"): cv.string,
        }
    )
    #    .extend(mqtt.MQTT_AVAILABILITY_SCHEMA.schema)
    .extend(mqtt.MQTT_JSON_ATTRS_SCHEMA.schema)
)


async def async_setup_platform(
    hass: HomeAssistantType, config: ConfigType, async_add_entities, discovery_info=None
):
    """Set up MQTT plant through configuration.yaml."""
    await async_setup_reload_service(hass, DOMAIN, PLATFORMS)
    await _async_setup_entity(config, async_add_entities)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up MQTT plant dynamically through MQTT discovery."""

    async def async_discover(discovery_payload):
        """Discover and add a MQTT plant."""

        discovery_data = discovery_payload.discovery_data
        try:
            _LOGGER.info("Adding plant entry: payload: %s", discovery_payload)
            config = PLATFORM_SCHEMA(discovery_payload)

            ent_reg = await entity_registry.async_get_registry(hass)
            for sensor, uid in config["sensors"].items():
                config["sensors"][sensor] = ent_reg.async_get_entity_id(
                    "sensor", "mqtt", uid
                )
            del config["sensors"]["timestamp"]

            await _async_setup_entity(
                config, async_add_entities, config_entry, discovery_data
            )
        except Exception:
            clear_discovery_hash(hass, discovery_data[ATTR_DISCOVERY_HASH])
            raise

    async_dispatcher_connect(
        hass, MQTT_DISCOVERY_NEW.format(plant.DOMAIN, "mqtt"), async_discover
    )


async def _async_setup_entity(
    config, async_add_entities, config_entry=None, discovery_data=None
):
    """Set up the MQTT Plant."""
    async_add_entities([MqttPlant(config, config_entry, discovery_data)])


class MqttPlant(
    MqttAttributes, MqttAvailability, MqttDiscoveryUpdate, MqttEntityDeviceInfo, Plant
):
    """representation of a MQTT plant."""

    def __init__(self, config, config_entry, discovery_data):
        """Initialize the MQTT Plant."""
        self._config = config
        self._unique_id = config.get(CONF_UNIQUE_ID)

        device_config = config.get(CONF_DEVICE)

        _LOGGER.warn("Making plant %s", config["name"])
        Plant.__init__(self, config["name"], config)
        MqttAttributes.__init__(self, config)
        MqttAvailability.__init__(self, config)
        MqttDiscoveryUpdate.__init__(self, discovery_data, self.discovery_update)
        MqttEntityDeviceInfo.__init__(self, device_config, config_entry)

    async def async_added_to_hass(self):
        """Subscribe MQTT events."""
        await super().async_added_to_hass()

    async def discovery_update(self, discovery_payload):
        """Handle updated discovery message."""
        config = PLATFORM_SCHEMA(discovery_payload)
        await self.attributes_discovery_update(config)
        await self.availability_discovery_update(config)
        await self.device_info_discovery_update(config)
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self):
        """Unsubscribe when removed."""
        await MqttAttributes.async_will_remove_from_hass(self)
        await MqttAvailability.async_will_remove_from_hass(self)
        await MqttDiscoveryUpdate.async_will_remove_from_hass(self)
