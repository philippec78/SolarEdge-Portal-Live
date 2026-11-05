"""Sensors for the live SolarEdge power flow."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import UnitOfPower
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import PortalCoordinator, PortalEntry
from .const import CONF_SITE_ID, DOMAIN


async def async_setup_entry(hass, entry: PortalEntry, async_add_entities):
    site = entry.data[CONF_SITE_ID]
    async_add_entities(
        PortalSensor(entry.runtime_data, site, key)
        for key in ("grid", "imported", "exported", "production", "consumption", "timestamp")
    )


class PortalSensor(CoordinatorEntity[PortalCoordinator], SensorEntity):
    """Expose one value of the shared portal reading."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: PortalCoordinator, site: str, key: str) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_unique_id = f"{site}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, site)}, name=f"SolarEdge Live {site}",
            manufacturer="SolarEdge",
            configuration_url=f"https://monitoring.solaredge.com/one#/residential/dashboard?siteId={site}",
        )
        if key == "timestamp":
            self._attr_device_class = SensorDeviceClass.TIMESTAMP
        else:
            self._attr_device_class = SensorDeviceClass.POWER
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_native_unit_of_measurement = UnitOfPower.WATT

    @property
    def native_value(self):
        return getattr(self.coordinator.data, self._key)

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data
        return {
            "source_status": data.source_status,
            "source_timestamp": data.timestamp.isoformat() if data.timestamp else None,
        }

    @property
    def available(self) -> bool:
        return super().available and self.native_value is not None
