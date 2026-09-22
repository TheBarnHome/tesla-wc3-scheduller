"""Transport vers l'API Fleet de Tesla.

Le jeton n'est jamais stocke ni configure : il est demande a l'entree de
configuration de l'integration ``tesla_fleet``, qui le rafraichit elle-meme via
``OAuth2Session.async_ensure_token_valid``. C'est tout l'interet de ce composant
par rapport a un ``rest_command`` alimente par un jeton fige dans les secrets.
"""

from __future__ import annotations

import logging
from typing import Any

from aiohttp import ClientError
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.config_entry_oauth2_flow import (
    OAuth2Session,
    async_get_config_entry_implementation,
)
from jwt import PyJWTError, decode

from .const import (
    DEFAULT_REGION,
    DEFAULT_TIME_ZONE_ID,
    IDENTIFIER_TYPE_WALL_CONNECTOR_DIN,
    REGION_BASE_URLS,
    REQUEST_TIMEOUT,
    TESLA_FLEET_DOMAIN,
    USER_AGENT,
)

_LOGGER = logging.getLogger(__name__)


class TeslaWallConnectorError(HomeAssistantError):
    """Erreur de communication avec l'API Fleet."""


async def async_get_access_token(hass: HomeAssistant) -> str:
    """Retourne un jeton d'acces valide, rafraichi si besoin.

    Le jeton appartient a l'entree de configuration ``tesla_fleet`` : on ne le
    copie jamais, on le demande a chaque appel.
    """
    entries = hass.config_entries.async_entries(TESLA_FLEET_DOMAIN)
    if not entries:
        raise TeslaWallConnectorError(
            f"L'integration {TESLA_FLEET_DOMAIN} doit etre configuree : "
            "c'est elle qui fournit et rafraichit le jeton d'acces."
        )

    entry = entries[0]
    implementation = await async_get_config_entry_implementation(hass, entry)
    session = OAuth2Session(hass, entry, implementation)
    await session.async_ensure_token_valid()
    return session.token["access_token"]


def region_base_url(access_token: str) -> str:
    """Deduit l'endpoint Fleet regional depuis les claims du jeton.

    L'integration officielle fait exactement la meme chose avec ``ou_code``.
    En cas de jeton illisible on retombe sur l'Europe, surchargeable par le
    parametre ``base_url`` du service.
    """
    try:
        claims = decode(access_token, options={"verify_signature": False})
    except PyJWTError:
        _LOGGER.debug("Jeton illisible, region par defaut %s", DEFAULT_REGION)
        return REGION_BASE_URLS[DEFAULT_REGION]

    region = str(claims.get("ou_code", DEFAULT_REGION)).lower()
    return REGION_BASE_URLS.get(region, REGION_BASE_URLS[DEFAULT_REGION])


def build_charge_schedule_payload(
    *,
    wall_connector_din: str,
    enable_schedule: bool,
    day_time_periods: list[dict[str, Any]],
    time_zone_id: str = DEFAULT_TIME_ZONE_ID,
) -> dict[str, Any]:
    """Construit le corps gRPC de ``configure_charge_schedule_request``.

    La forme du message est imposee par la passerelle : c'est celle que la
    commande ``rest_command`` d'origine envoyait deja.
    """
    return {
        "command_type": "grpc_command",
        "command_properties": {
            "message": {
                "wc": {
                    "configure_charge_schedule_request": {
                        "config": {
                            "schedule": {"day_time_periods": day_time_periods},
                            "delay": {"max_delay_seconds": 0},
                            "enable_schedule": enable_schedule,
                        },
                        "time_zone": {
                            "time_zone_id": time_zone_id,
                            "time_zone_info": {
                                "transitions": [
                                    {
                                        "local_time_utc_offset": 0,
                                        "timestamp": {"nanos": 0, "seconds": 0},
                                    }
                                ]
                            },
                        },
                    }
                }
            },
            "identifier_type": IDENTIFIER_TYPE_WALL_CONNECTOR_DIN,
            "target_id": wall_connector_din,
        },
    }


async def async_configure_charge_schedule(
    hass: HomeAssistant,
    *,
    access_token: str,
    base_url: str,
    energy_site_id: int,
    wall_connector_din: str,
    enable_schedule: bool,
    day_time_periods: list[dict[str, Any]],
    time_zone_id: str = DEFAULT_TIME_ZONE_ID,
) -> dict[str, Any]:
    """Envoie le planning a une borne et retourne la reponse de l'API Fleet."""
    payload = build_charge_schedule_payload(
        wall_connector_din=wall_connector_din,
        enable_schedule=enable_schedule,
        day_time_periods=day_time_periods,
        time_zone_id=time_zone_id,
    )

    session = async_get_clientsession(hass)
    url = f"{base_url}/api/1/energy_sites/{energy_site_id}/command"

    _LOGGER.debug(
        "Commande planning vers la borne %s du site %s (%s)",
        wall_connector_din,
        energy_site_id,
        base_url,
    )

    try:
        async with session.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {access_token}",
                "User-Agent": USER_AGENT,
            },
            timeout=REQUEST_TIMEOUT,
        ) as response:
            if response.status == 401:
                raise TeslaWallConnectorError(
                    "L'API Fleet a refuse le jeton (401). Verifie que "
                    f"l'integration {TESLA_FLEET_DOMAIN} est bien connectee."
                )
            if response.status >= 400:
                body = await response.text()
                raise TeslaWallConnectorError(
                    f"L'API Fleet a repondu {response.status} : {body[:300]}"
                )
            data: dict[str, Any] = await response.json(content_type=None)
    except ClientError as err:
        raise TeslaWallConnectorError(f"API Fleet injoignable : {err}") from err

    result = data.get("response", data)
    code = result.get("code") if isinstance(result, dict) else None
    if code not in (None, 0):
        raise TeslaWallConnectorError(
            f"L'API Fleet a refuse la commande (code {code}) : {result}"
        )

    return data
