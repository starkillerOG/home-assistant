"""Support for Netgear routers."""
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, DATA_MEGABYTES
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .router import NetgearDeviceEntity, NetgearRouterEntity, NetgearRouter, async_setup_netgear_entry
from .const import (
    DOMAIN,
    KEY_COORDINATOR,
    KEY_ROUTER,
)

SENSOR_TYPES = {
    "type": SensorEntityDescription(
        key="type",
        name="link type",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "link_rate": SensorEntityDescription(
        key="link_rate",
        name="link rate",
        native_unit_of_measurement="Mbps",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "signal": SensorEntityDescription(
        key="signal",
        name="signal strength",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "ssid": SensorEntityDescription(
        key="ssid",
        name="ssid",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "conn_ap_mac": SensorEntityDescription(
        key="conn_ap_mac",
        name="access point mac",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
}

SENSOR_TRAFFIC_TYPES = {
    "NewTodayUpload": SensorEntityDescription(
        key="NewTodayUpload",
        name="Upload today",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=DATA_MEGABYTES,
    ),
    "NewTodayDownload": SensorEntityDescription(
        key="NewTodayDownload",
        name="Download today",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=DATA_MEGABYTES,
    ),
    "NewYesterdayUpload": SensorEntityDescription(
        key="NewYesterdayUpload",
        name="Upload yesterday",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=DATA_MEGABYTES,
    ),
    "NewYesterdayDownload": SensorEntityDescription(
        key="NewYesterdayDownload",
        name="Download yesterday",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=DATA_MEGABYTES,
    ),
    "NewWeekUpload": SensorEntityDescription(
        key="NewWeekUpload",
        name="Upload week",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=DATA_MEGABYTES,
    ),
    "NewWeekDownload": SensorEntityDescription(
        key="NewWeekDownload",
        name="Download week",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=DATA_MEGABYTES,
    ),
    "NewMonthUpload": SensorEntityDescription(
        key="NewMonthUpload",
        name="Upload month",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=DATA_MEGABYTES,
    ),
    "NewMonthDownload": SensorEntityDescription(
        key="NewMonthDownload",
        name="Download month",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=DATA_MEGABYTES,
    ),
    "NewLastMonthUpload": SensorEntityDescription(
        key="NewLastMonthUpload",
        name="Upload last month",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=DATA_MEGABYTES,
    ),
    "NewLastMonthDownload": SensorEntityDescription(
        key="NewLastMonthDownload",
        name="Download last month",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=DATA_MEGABYTES,
    ),
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up device tracker for Netgear component."""

    def generate_sensor_classes(
        coordinator: DataUpdateCoordinator, router: NetgearRouter, device: dict
    ):
        sensors = ["type", "link_rate", "signal"]
        if router.method_version == 2:
            sensors.extend(["ssid", "conn_ap_mac"])

        return [
            NetgearSensorEntity(coordinator, router, device, attribute)
            for attribute in sensors
        ]

    async_setup_netgear_entry(hass, entry, async_add_entities, generate_sensor_classes)
    
    router = hass.data[DOMAIN][entry.unique_id][KEY_ROUTER]
    coordinator = hass.data[DOMAIN][entry.unique_id][KEY_COORDINATOR]
    entities = []
    
    for attribute in SENSOR_TRAFFIC_TYPES:
        entities.append(
            NetgearRouterTrafficEntity(
                coordinator, router, attribute
            )
        )
        
    async_add_entities(entities)


class NetgearSensorEntity(NetgearDeviceEntity, SensorEntity):
    """Representation of a device connected to a Netgear router."""

    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        router: NetgearRouter,
        device: dict,
        attribute: str,
    ) -> None:
        """Initialize a Netgear device."""
        super().__init__(coordinator, router, device)
        self._attribute = attribute
        self.entity_description = SENSOR_TYPES[self._attribute]
        self._name = f"{self.get_device_name()} {self.entity_description.name}"
        self._unique_id = f"{self._mac}-{self._attribute}"
        self._state = self._device.get(self._attribute)

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return self._state

    @callback
    def async_update_device(self) -> None:
        """Update the Netgear device."""
        self._device = self._router.devices[self._mac]
        self._active = self._device["active"]
        if self._device.get(self._attribute) is not None:
            self._state = self._device[self._attribute]

class NetgearRouterTrafficEntity(NetgearRouterEntity, SensorEntity):
    """Representation of a device connected to a Netgear router."""

    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        router: NetgearRouter,
        attribute: str,
    ) -> None:
        """Initialize a Netgear device."""
        super().__init__(coordinator, router)
        self._attribute = attribute
        self.entity_description = SENSOR_TYPES[self._attribute]
        self._name = f"{router.device_name} {self.entity_description.name}"
        self._unique_id = f"{router.serial_number}-{self._attribute}"
        self._traffic = None
        self._traffic_avg = None
        self._traffic_avg_attr = f"{self.entity_description.name} average"
        self.async_update_device()

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return self._traffic

    @property
    def extra_state_attributes(self):
        """Return device specific state attributes."""
        extra_attr = {}
        if self._traffic_avg is not None:
            extra_attr[self._traffic_avg_attr] = self._traffic_avg
        return extra_attr

    @callback
    def async_update_device(self) -> None:
        """Update the Netgear device."""
        if self._router.traffic_data is not None:
            data = self._router.traffic_data.get(self._attribute)
            if isinstance(data, float):
                self._traffic = data
            elif isinstance(data, tuple):
                self._traffic = data[0]
                self._traffic_avg = data[1]

    async def async_added_to_hass(self):
        """Entity added to hass."""
        self._router.N_traffic_meter = self._router.N_traffic_meter + 1
        await super().async_added_to_hass()

    async def async_will_remove_from_hass(self):
        """Entity removed from hass."""
        self._router.N_traffic_meter = self._router.N_traffic_meter - 1
        await super().async_will_remove_from_hass()