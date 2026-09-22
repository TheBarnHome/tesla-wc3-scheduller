"""Transport vers l'API Fleet de Tesla.

Le jeton n'est jamais stocke ni configure : il est demande a l'entree de
configuration de l'integration ``tesla_fleet``, qui le rafraichit elle-meme via
``OAuth2Session.async_ensure_token_valid``. C'est tout l'interet de ce composant
par rapport a un ``rest_command`` alimente par un jeton fige dans les secrets.
"""

from __future__ import annotations

import json
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
from homeassistant.util import dt as dt_util
from jwt import PyJWTError, decode

from .const import (
    CHARGE_SCHEDULE_ERROR_NONE,
    CHARGE_SCHEDULE_ERRORS,
    CHARGE_SCHEDULE_RESPONSE,
    DEFAULT_REGION,
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
    time_zone_id: str = "UTC",
    utc_offset_seconds: int = 0,
) -> dict[str, Any]:
    """Construit le corps gRPC de ``configure_charge_schedule_request``.

    La forme du message est imposee par la passerelle : c'est celle que la
    commande ``rest_command`` d'origine envoyait deja.

    Les periodes sont lues par la borne **dans le fuseau declare ici**. Verifie
    sur la borne : une fenetre 20:00-21:00 annoncee en UTC autorise la charge a
    22:00 heure de Paris. Declarer ``UTC`` avec un decalage nul signifie donc
    que les heures envoyees sont UTC, et l'application Tesla les affiche telles
    quelles. Pour raisonner en heure locale, il faut declarer la zone locale et
    son decalage courant, puis envoyer des heures locales.
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
                                        "local_time_utc_offset": utc_offset_seconds,
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


def charge_schedule_error(data: Any) -> int | None:
    """Retourne le code d'erreur que la borne a renvoye, ou None s'il est absent.

    L'API Fleet enveloppe la reponse protobuf : le code utile vit dans
    ``...Payload.Wc.Message.ConfigureChargeScheduleResponse.error``, et
    ``WCChargeScheduleError`` place ``NONE`` a 1. Un champ absent ne dit rien,
    seul un code lu est juge.
    """

    def walk(node: Any) -> int | None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == CHARGE_SCHEDULE_RESPONSE and isinstance(value, dict):
                    code = value.get("error")
                    return code if isinstance(code, int) else None
                found = walk(value)
                if found is not None:
                    return found
        elif isinstance(node, list):
            for item in node:
                found = walk(item)
                if found is not None:
                    return found
        return None

    return walk(data)


async def async_configure_charge_schedule(
    hass: HomeAssistant,
    *,
    access_token: str,
    base_url: str,
    energy_site_id: int,
    wall_connector_din: str,
    enable_schedule: bool,
    day_time_periods: list[dict[str, Any]],
    time_zone_id: str | None = None,
) -> dict[str, Any]:
    """Envoie le planning a une borne et retourne la reponse de l'API Fleet.

    Le fuseau declare par defaut est celui de Home Assistant, avec le decalage
    courant : les periodes sont alors des heures locales, celles que l'on lit
    dans l'application Tesla, et le passage a l'heure d'hiver est couvert par
    le decalage recalcule a chaque appel.
    """
    local_now = dt_util.now()
    offset = local_now.utcoffset()

    payload = build_charge_schedule_payload(
        wall_connector_din=wall_connector_din,
        enable_schedule=enable_schedule,
        day_time_periods=day_time_periods,
        time_zone_id=time_zone_id or hass.config.time_zone,
        utc_offset_seconds=int(offset.total_seconds()) if offset else 0,
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

    # Un HTTP 200 ne suffit pas : la borne juge la commande et renvoie son
    # propre code, ou NONE vaut 1. Sans ce controle, un refus (borne hors
    # ligne, memoire non inscriptible) passerait pour un succes.
    error = charge_schedule_error(data)
    if error is not None and error != CHARGE_SCHEDULE_ERROR_NONE:
        label = CHARGE_SCHEDULE_ERRORS.get(error, f"code {error}")
        request_id = ""
        if isinstance(result, dict) and result.get("request_id"):
            request_id = f" (request_id {result['request_id']})"
        raise TeslaWallConnectorError(
            f"La borne {wall_connector_din} a refuse le planning : {label}"
            f"{request_id}. Reponse : {json.dumps(data)[:300]}"
        )

    return data
