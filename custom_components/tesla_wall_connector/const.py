"""Constantes de l'integration Tesla Wall Connector."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "tesla_wall_connector"

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

# Le planning des bornes est exprime en UTC : c'est ce que calculent les
# automatisations, et cela evite toute dependance aux transitions d'heure.
DEFAULT_TIME_ZONE_ID: Final = "UTC"

# Valeur utilisee par Tesla pour designer une borne par son DIN.
# Aligne sur tesla_fleet_api.const.EnergyDeviceIdentifierType.WALL_CONNECTOR_DIN.
IDENTIFIER_TYPE_WALL_CONNECTOR_DIN: Final = 4

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
