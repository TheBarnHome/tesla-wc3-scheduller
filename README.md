# Tesla Wall Connector pour Home Assistant

Piloter le planning de charge interne de bornes Tesla Wall Connector depuis
Home Assistant, **avec le jeton OAuth de l'integration `tesla_fleet`**, donc
sans jeton fige qui expire.

## Le probleme resolu

Home Assistant expose les Wall Connectors a travers l'integration core
`tesla_fleet` : les capteurs remontent, le coordonnateur interroge la passerelle,
mais **aucun module de commande ne les adresse**. `switch.py`, `number.py`,
`select.py` et `button.py` de l'integration ne mentionnent jamais les bornes.
Seul `sensor.py` les lit.

La seule facon de commander une borne etait donc d'ecrire soi-meme l'appel HTTP
vers l'API Fleet, avec un jeton d'acces recopie dans `secrets.yaml`. Or ce jeton
expire en quelques heures.

L'integration officielle, elle, ne stocke jamais de jeton : elle passe un
callback qui en reclame un valide a chaque requete.

```python
async def _get_access_token() -> str:
    await oauth_session.async_ensure_token_valid()
    return oauth_session.token[CONF_ACCESS_TOKEN]
```

Ce composant fait la meme chose : il demande le jeton a l'entree de
configuration `tesla_fleet`, qui le rafraichit, puis envoie la commande gRPC
`configure_charge_schedule_request` a la borne visee.

## Ce que fait le composant

Un seul service : `tesla_wc3_schedule.configure_charge_schedule`. Il envoie le
planning a une ou plusieurs bornes, designees par leur DIN.

## Prerequis

- Home Assistant 2024.1 ou plus recent ;
- l'integration `tesla_fleet` configuree et connectee — c'est elle qui detient le
  jeton, et elle doit avoir le scope `energy_cmds`, ce que Home Assistant
  demande par defaut.

## Installation

### Par HACS

1. HACS > Integrations > les trois points > Depots personnalises ;
2. ajouter l'URL de ce depot, categorie **Integration** ;
3. installer « Tesla Wall Connector », puis redemarrer Home Assistant.

### A la main

Copier `custom_components/tesla_wc3_schedule/` dans le dossier
`custom_components/` de la configuration Home Assistant, puis redemarrer.

## Configuration

Ajouter la ligne suivante dans `configuration.yaml` :

```yaml
tesla_wc3_schedule:
```

Aucun autre reglage : le site d'energie et les bornes sont passes au service.

Le domaine est volontairement distinct de `tesla_wall_connector` : Home
Assistant core expose deja une integration de ce nom, qui lit les bornes en
local et les decouvre en DHCP. Un composant custom du meme domaine la masque,
et faute de `config_flow` cote custom, chaque decouverte echoue en erreur.

## Le service

| Champ | Requis | Description |
| --- | --- | --- |
| `energy_site_id` | oui | Identifiant du site d'energie qui porte les bornes. |
| `wall_connector_dins` | oui | Un ou plusieurs DIN, separes par des virgules. |
| `enable_schedule` | oui | Active ou desactive le planning interne. |
| `day_time_periods` | oui | Periodes au format Tesla, en JSON ou en YAML. |
| `base_url` | non | Force l'endpoint regional ; deduit du jeton sinon. |
| `time_zone_id` | non | Laisser `UTC`. |
| `dry_run` | non | Valide le jeton et la cible sans rien envoyer. |

Le service renvoie la reponse de l'API Fleet, borne par borne, si l'appel est
fait avec `return_response: true`.

### Verifier l'authentification sans rien modifier

```yaml
action: tesla_wc3_schedule.configure_charge_schedule
data:
  energy_site_id: 1234567890123456
  wall_connector_dins: "1XXXXXXXXXXXXX,2XXXXXXXXXXXXX"
  enable_schedule: true
  day_time_periods:
    - day_bitmask: 127
      time_periods:
        - start_seconds: 79200
          end_seconds: 82800
  dry_run: true
response_variable: resultat
```

## Migration depuis un `rest_command`

Le service remplace le `rest_command` **et** la boucle sur les DIN : il adresse
lui-meme chaque borne de la liste.

Avant :

```yaml
sequence:
  - variables:
      wall_connector_dins: "1XXXXXXXXXXXXX,2XXXXXXXXXXXXX"
  - repeat:
      for_each: >-
        {{ wall_connector_dins.split(',') | map('trim') | reject('eq', '') | list }}
      sequence:
        - service: rest_command.tesla_wall_connector_configure_charge_schedule
          data:
            base_url: https://fleet-api.prd.eu.vn.cloud.tesla.com
            access_token: !secret tesla_access_token
            energy_site_id: 1234567890123456
            wall_connector_din: "{{ repeat.item }}"
            enable_schedule: "{{ enable_schedule | bool }}"
            day_time_periods_json: "{{ day_time_periods_json }}"
```

Apres :

```yaml
sequence:
  - action: tesla_wc3_schedule.configure_charge_schedule
    data:
      energy_site_id: 1234567890123456
      wall_connector_dins: "1XXXXXXXXXXXXX,2XXXXXXXXXXXXX"
      enable_schedule: "{{ enable_schedule | bool }}"
      day_time_periods: "{{ day_time_periods_json }}"
```

Le jeton et l'URL d'endpoint n'ont plus a etre stockes nulle part : le premier
venait d'un secret qu'il faut supprimer, la seconde est deduite du jeton.

La logique metier des automatisations ne bouge pas, y compris l'astuce de la
fenetre UTC deja ecoulee : une borne TWC3 refuse une liste `day_time_periods`
vide, meme lorsque le planning est desactive.

## Limites connues

- **UTC uniquement.** Le message declare un decalage nul, seules des periodes
  exprimees en UTC sont donc correctes.
- **Pas d'interface de configuration.** Le service prend le site et les bornes
  en parametres, ce qui garde la configuration dans Git plutot que dans
  `.storage`. Un config flow pourra venir plus tard.
- **Un seul site d'energie.** Le premier site portant des bornes est suppose
  etre le bon.

## Notes techniques

Ce composant s'appuie uniquement sur des API publiques de Home Assistant :

- `homeassistant.helpers.config_entry_oauth2_flow.async_get_config_entry_implementation`
- `homeassistant.helpers.config_entry_oauth2_flow.OAuth2Session`
- `homeassistant.helpers.aiohttp_client.async_get_clientsession`

Le corps envoye reproduit celui de la passerelle :

```json
{
  "command_type": "grpc_command",
  "command_properties": {
    "message": {"wc": {"configure_charge_schedule_request": { }}},
    "identifier_type": 4,
    "target_id": "<DIN de la borne>"
  }
}
```

`identifier_type: 4` vaut `EnergyDeviceIdentifierType.WALL_CONNECTOR_DIN`. Le
`target_id` est indispensable des qu'un site porte plusieurs bornes : sans lui,
la commande ne sait pas quelle borne viser.

La bibliotheque `tesla_fleet_api` installee avec Home Assistant possede deja une
methode `_command()` sur le client de site d'energie, qui poste sur le meme
endpoint. Elle n'est pas utilisee ici parce qu'elle n'emet pas de `target_id`.

Un HTTP 200 ne veut pas dire que la borne a accepte : elle renvoie sa propre
enumeration `WCChargeScheduleError`, ou `NONE` vaut **1** et `INVALID` vaut 0.
Un `error: 1` est donc un succes, et le composant refuse tout autre code
(`NO_INTERNET`, `NON_VOLATILE_DATA_READ_WRITE_FAIL`, `INTERNAL`) en citant le
`request_id` de l'appel, pour qu'une commande rejetee ne passe pas inapercue
dans une automatisation.

## Licence

MIT.
