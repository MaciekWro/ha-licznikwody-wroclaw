"""Sensory MPWiK Wrocław."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import MpwikConfigEntry
from .const import CONF_ADRES, DOMAIN, REMOVED_SENSOR_KEYS
from .coordinator import MpwikCoordinator, MpwikData


@dataclass(frozen=True, kw_only=True)
class MpwikSensorDescription(SensorEntityDescription):
    value_fn: Callable[[MpwikData], Any]
    attrs_fn: Callable[[MpwikData], dict[str, Any]] = lambda _: {}


SENSORS: tuple[MpwikSensorDescription, ...] = (
    MpwikSensorDescription(
        key="stan_wodomierza",
        translation_key="stan_wodomierza",
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        suggested_display_precision=3,
        value_fn=lambda d: d.stan_wodomierza,
        attrs_fn=lambda d: {"czas_odczytu": d.stan_wodomierza_czas, "licznik": d.licznik},
    ),
    MpwikSensorDescription(
        key="zuzycie_dzienne",
        translation_key="zuzycie_dzienne",
        device_class=SensorDeviceClass.WATER,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        suggested_display_precision=3,
        value_fn=lambda d: d.zuzycie_dzienne,
        attrs_fn=lambda d: {"dzien": d.zuzycie_dzienne_dzien, "do_godziny": d.ostatnia_godzina},
    ),
    MpwikSensorDescription(
        key="zuzycie_godzinowe",
        translation_key="zuzycie_godzinowe",
        device_class=SensorDeviceClass.WATER,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        suggested_display_precision=3,
        value_fn=lambda d: d.zuzycie_godzinowe,
        attrs_fn=lambda d: {
            "od": d.ostatnia_godzina - timedelta(hours=1) if d.ostatnia_godzina else None,
            "do": d.ostatnia_godzina,
        },
    ),
    MpwikSensorDescription(
        key="ostatnia_godzina",
        translation_key="ostatnia_godzina",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: d.ostatnia_godzina,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MpwikConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    registry = er.async_get(hass)
    base_id = f"{coordinator.podmiot}_{coordinator.punkt}"
    for key in REMOVED_SENSOR_KEYS:
        if entity_id := registry.async_get_entity_id("sensor", DOMAIN, f"{base_id}_{key}"):
            registry.async_remove(entity_id)
    async_add_entities(MpwikSensor(coordinator, description) for description in SENSORS)


class MpwikSensor(CoordinatorEntity[MpwikCoordinator], SensorEntity):
    _attr_has_entity_name = True
    entity_description: MpwikSensorDescription

    def __init__(self, coordinator: MpwikCoordinator, description: MpwikSensorDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        base_id = f"{coordinator.podmiot}_{coordinator.punkt}"
        self._attr_unique_id = f"{base_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, base_id)},
            name=f"Wodomierz {coordinator.config_entry.data.get(CONF_ADRES, coordinator.punkt)}",
            manufacturer="ML",
            model=f"Punkt {coordinator.punkt}",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=f"https://ebok.mpwik.wroc.pl/trust/zuzycie-wody?p={coordinator.podmiot}",
        )

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self.entity_description.attrs_fn(self.coordinator.data)
