"""Pilotage des Tesla Wall Connectors avec le jeton de l'integration tesla_fleet.

Home Assistant expose les Wall Connectors a travers l'integration core
``tesla_fleet``, mais en lecture seule : aucun de ses modules de commande
(switch, number, select, button) ne les adresse. Ce composant ajoute la seule
piece manquante, l'envoi des commandes gRPC, en reutilisant le jeton OAuth de
l'integration officielle plutot qu'un jeton fige dans les secrets.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .api import (
    TeslaWallConnectorError,
    async_configure_charge_schedule,
    async_get_access_token,
    region_base_url,
)
from .const import (
    CONF_BASE_URL,
    CONF_DAY_TIME_PERIODS,
    CONF_DRY_RUN,
    CONF_ENABLE_SCHEDULE,
    CONF_ENERGY_SITE_ID,
    CONF_TIME_ZONE_ID,
    CONF_WALL_CONNECTOR_DINS,
    DEFAULT_TIME_ZONE_ID,
    DOMAIN,
    SERVICE_CONFIGURE_CHARGE_SCHEDULE,
)

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema({DOMAIN: vol.Schema({})}, extra=vol.ALLOW_EXTRA)

SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ENERGY_SITE_ID): vol.Coerce(int),
        vol.Required(CONF_WALL_CONNECTOR_DINS): vol.Any(str, [str]),
        vol.Required(CONF_ENABLE_SCHEDULE): cv.boolean,
        vol.Required(CONF_DAY_TIME_PERIODS): vol.Any(str, list),
        vol.Optional(CONF_BASE_URL): cv.url,
        vol.Optional(CONF_TIME_ZONE_ID, default=DEFAULT_TIME_ZONE_ID): cv.string,
        vol.Optional(CONF_DRY_RUN, default=False): cv.boolean,
    }
)


def _as_din_list(value: str | list[str]) -> list[str]:
    """Accepte la forme "din1,din2" comme une vraie liste de DIN."""
    if isinstance(value, str):
        items: list[str] = value.split(",")
    else:
        items = [str(item) for item in value]

    dins = [item.strip() for item in items if item.strip()]
    if not dins:
        raise HomeAssistantError("wall_connector_dins ne contient aucune borne.")
    return dins


def _as_day_time_periods(value: str | list[Any]) -> list[dict[str, Any]]:
    """Accepte le JSON produit par les automatisations, ou une liste native."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as err:
            raise HomeAssistantError(
                f"day_time_periods n'est pas un JSON valide : {err}"
            ) from err

    if not isinstance(value, list) or not value:
        raise HomeAssistantError("day_time_periods doit etre une liste non vide.")
    return value


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Enregistre le service des le demarrage de Home Assistant."""

    async def _async_configure_charge_schedule(
        call: ServiceCall,
    ) -> dict[str, Any]:
        dins = _as_din_list(call.data[CONF_WALL_CONNECTOR_DINS])
        day_time_periods = _as_day_time_periods(call.data[CONF_DAY_TIME_PERIODS])
        enable_schedule: bool = call.data[CONF_ENABLE_SCHEDULE]
        dry_run: bool = call.data[CONF_DRY_RUN]

        try:
            access_token = await async_get_access_token(hass)
        except TeslaWallConnectorError as err:
            raise HomeAssistantError(str(err)) from err

        base_url = call.data.get(CONF_BASE_URL) or region_base_url(access_token)

        results: dict[str, Any] = {}
        for din in dins:
            if dry_run:
                # Valide le jeton et la cible sans rien modifier sur la borne.
                results[din] = {
                    "dry_run": True,
                    "base_url": base_url,
                    "energy_site_id": call.data[CONF_ENERGY_SITE_ID],
                    "enable_schedule": enable_schedule,
                }
                continue

            try:
                results[din] = await async_configure_charge_schedule(
                    hass,
                    access_token=access_token,
                    base_url=base_url,
                    energy_site_id=call.data[CONF_ENERGY_SITE_ID],
                    wall_connector_din=din,
                    enable_schedule=enable_schedule,
                    day_time_periods=day_time_periods,
                    time_zone_id=call.data[CONF_TIME_ZONE_ID],
                )
            except TeslaWallConnectorError as err:
                raise HomeAssistantError(str(err)) from err

            _LOGGER.debug("Planning applique a la borne %s", din)

        return {"results": results}

    hass.services.async_register(
        DOMAIN,
        SERVICE_CONFIGURE_CHARGE_SCHEDULE,
        _async_configure_charge_schedule,
        schema=SERVICE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )

    return True
