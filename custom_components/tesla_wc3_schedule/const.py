"""Constantes de l'integration Tesla Wall Connector."""

from __future__ import annotations

from typing import Final

# Ne pas reprendre le domaine ``tesla_wall_connector`` : Home Assistant core
# expose deja une integration de ce nom, qui lit les bornes en local et les
# decouvre en DHCP. Un composant custom du meme domaine la masque, et comme
# celui-ci n'expose pas de config_flow, chaque decouverte echoue en erreur.
DOMAIN: Final = "tesla_wc3_schedule"

# L'integration officielle qui detient le jeton OAuth et le rafraichit.
TESLA_FLEET_DOMAIN: Final = "tesla_fleet"

# Champs du service.
CONF_BASE_URL: Final = "base_url"
CONF_DAY_TIME_PERIODS: Final = "day_time_periods"
CONF_DRY_RUN: Final = "dry_run"
CONF_ENABLE_SCHEDULE: Final = "enable_schedule"
CONF_ENERGY_SITE_ID: Final = "energy_site_id"
CONF_TIME_ZONE_ID: Final = "time_zone_id"
CONF_WALL_CONNECTOR_DINS: Final = "wall_connector_dins"

SERVICE_CONFIGURE_CHARGE_SCHEDULE: Final = "configure_charge_schedule"

# La borne lit les periodes dans le fuseau declare au moment de l'envoi, et
# l'application Tesla affiche ces memes heures. Le service declare donc par
# defaut la zone de Home Assistant avec son decalage courant, ce qui rend les
# periodes locales ; un fuseau explicite reste possible via ``time_zone_id``.
# Il n'y a plus de constante de fuseau par defaut.

# Valeur utilisee par Tesla pour designer une borne par son DIN.
# Aligne sur tesla_fleet_api.const.EnergyDeviceIdentifierType.WALL_CONNECTOR_DIN.
IDENTIFIER_TYPE_WALL_CONNECTOR_DIN: Final = 4

# Enumeration WCChargeScheduleError du protocole de la borne. Elle se lit a
# l'envers : NONE vaut 1 et INVALID vaut 0, donc un ``error: 1`` dans la
# reponse est un succes.
CHARGE_SCHEDULE_ERROR_NONE: Final = 1

CHARGE_SCHEDULE_ERRORS: Final = {
    0: "INVALID",
    1: "NONE",
    2: "NO_INTERNET",
    3: "NON_VOLATILE_DATA_READ_WRITE_FAIL",
    4: "INTERNAL",
}

# Nom du message protobuf qui porte ce code dans la reponse de l'API Fleet.
CHARGE_SCHEDULE_RESPONSE: Final = "ConfigureChargeScheduleResponse"

# Endpoints Fleet regionaux, alignes sur tesla_fleet_api.const.REGIONS.
REGION_BASE_URLS: Final = {
    "na": "https://fleet-api.prd.na.vn.cloud.tesla.com",
    "eu": "https://fleet-api.prd.eu.vn.cloud.tesla.com",
    "cn": "https://fleet-api.prd.cn.vn.cloud.tesla.cn",
}
DEFAULT_REGION: Final = "eu"

REQUEST_TIMEOUT: Final = 30

# Identifie le client aupres de l'API Fleet. Volontairement neutre : ce depot
# est public, rien de propre a une installation ne doit s'y trouver.
USER_AGENT: Final = "tesla-wc3-scheduller"
