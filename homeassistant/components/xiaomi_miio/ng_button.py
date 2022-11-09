"""Support for Xiaomi Miio button entities."""
from __future__ import annotations

from typing import Callable

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.components.xiaomi_miio.device import XiaomiMiioEntity
from homeassistant.helpers.entity import EntityCategory


class XiaomiButton(XiaomiMiioEntity, ButtonEntity):
    """Representation of Xiaomi button."""

    entity_description: ButtonEntityDescription
    method: Callable

    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_has_entity_name = True

    def __init__(self, button, device, entry, coordinator):
        """Initialize the plug switch."""
        self._name = button.name
        unique_id = f"{entry.unique_id}_button_{button.id}"
        self.method = button.method

        super().__init__(device, entry, unique_id, coordinator)

        # TODO: This should always be CONFIG for settables and non-configurable?
        category = EntityCategory(button.extras.get("entity_category", "config"))
        description = ButtonEntityDescription(
            key=button.id,
            name=button.name,
            icon=button.extras.get("icon"),
            device_class=button.extras.get("device_class"),
            entity_category=category,
        )

        self.entity_description = description

    async def async_press(self) -> None:
        """Press the button."""
        await self._try_command(
            f"Failed to execute button {self._name}",
            self.method,
        )
