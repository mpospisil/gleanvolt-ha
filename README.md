# Gleanvolt for Home Assistant

A native Home Assistant integration for [Gleanvolt](https://github.com/mpospisil/gleanvolt). It shows
the live data, lets you pick a charge mode and set what that mode needs, and starts and stops
charging. It talks to Gleanvolt's [HTTP API](https://github.com/mpospisil/gleanvolt/blob/main/docs/HTTP_API.md)
and **needs no MQTT broker**.

**Requires Gleanvolt 1.2.0 or later.** Setup reads the version from the controller and refuses an
older one, naming the version it found.

> **Use this integration or Gleanvolt's MQTT discovery, not both.** With both, the installation shows
> up as two devices with the same entities. MQTT discovery suits a setup that already runs a broker.
> This integration is the way to connect when there is no broker. It can also report a refusal back to
> the person who pressed the button, offers a real date-time entity, and has service actions with typed
> fields.

## Install

1. **In Gleanvolt**, open **Settings → Installation → API access**. Switch the API on, type
   `home-assistant` as the client's name, and press **Create key**. Then press **Restart** on
   **Settings → Health**. The key's name is what the log and each charging session record as the
   source of an action, for example *"API (home-assistant) started Targeted"*.
2. **In HACS**, open **⋮ → Custom repositories** and add `https://github.com/mpospisil/gleanvolt-ha`
   with the type **Integration**. Install **Gleanvolt**, then restart Home Assistant.
3. **Settings → Devices & services.** Gleanvolt announces itself on the network (`_gleanvolt._tcp`),
   so Home Assistant offers **Gleanvolt discovered** with the address filled in. Paste the key. If
   it isn't discovered, use **Add integration → Gleanvolt** and enter the host, the port (8090) and
   the key.

The form says what went wrong: the key was refused, nothing answered at that address, the API is
switched off (and where to switch it on), or Gleanvolt is older than 1.2.0.

Once it is set up:

- **Reconfigure** changes the host or port. The entities and their history stay, because they are
  tied to the installation's id and not to its address.
- **Re-authenticate** is offered on its own if the key stops working.
- **Configure** sets how often the live status is read: every 10 s by default, from 5 to 60 s.
- **Download diagnostics** gives the last answers from the controller, with the key removed.

## What you get

One device per installation. Its **software version** is the Gleanvolt build. **Visit** opens the web
UI. Each entity's meaning is described in Gleanvolt's
[Home Assistant page](https://github.com/mpospisil/gleanvolt/blob/main/docs/HOME_ASSISTANT.md#what-each-entity-means).

- **Live data.** The mode, the control state, the charger's status, solar, forecast, surplus, grid,
  battery and EV power, the currents, session energy and the battery loan. There are binary sensors
  for *Car connected*, *Charging now* and *Battery hold active*. Power and energy are set up for the
  energy dashboard, and **Grid price** is its *current price* entity.
- **The car** (*Car SOC*, *Car range*, *Car reading age*, *Car reading stale*) and **the tariff**
  (*Low tariff*, *Tariff change*, *Grid price*).
- **The running plan.** The *Forecasted* day plan, the *Targeted* plan and *Fast* progress. Each is
  `unknown` while its mode isn't running.
- **Controls that act at once.** **Charge mode** (select), **Start** and **Stop charging** (buttons), **Battery
  discharge hold**, **Fast low tariff only**, **SolarGrid low tariff only** and **Forecasted until
  full** (switches).
- **Parameters for the next start.** *Mode to start*, *Fast basis*, *Fast energy*, *Fast target SOC*, *Fast departure*,
  *Target basis*, *Target energy*, *Target SOC*, *Departure*, *Charge priority*, *Target rest SOC*,
  *Target sun only* and *Target low tariff only*.

### Starting a mode, like the web UI's tabs

The web UI's **Charging plan** has a tab per mode: you open one, set what it needs, and press **Start**.
The integration has the same three parts:

- **Mode to start** is the tab: which mode the parameters and the button are for. It is kept in Home
  Assistant and starts nothing by itself.
- The **parameters** for Fast and Targeted (*Fast basis*, *Fast energy*, *Departure*, …) are also kept in
  Home Assistant. They survive a Home Assistant restart and are sent only at a start.
- **Start** starts the mode in *Mode to start* with its parameters.

**Charge mode** always shows the mode Gleanvolt is actually in. Picking a mode there starts it straight
away with the same held parameters, and **Off** stops charging, as does **Stop charging**. If Gleanvolt
refuses, for example *Targeted* with no departure set, Home Assistant shows its reason and nothing
starts.

The device page lists every entity at once, because Home Assistant has no way to show only some.
[`dashboard/gleanvolt-card.yaml`](dashboard/gleanvolt-card.yaml) is a card that does: pick a mode in
*Mode to start*, and only that mode's controls and figures appear, the way a tab does. Replace
`gleanvolt_` in it with your device's entity prefix (for a device named *Home roof*:
`sed 's/\.gleanvolt_/.home_roof_/g'`), then in a dashboard **Edit → Add card → Manual** and paste.

Gleanvolt still boots in `Off` and starts charging only when asked. While a *Targeted* or *Fast*
charge runs, the plan sensors show the running request, wherever it was started. The held entities
show the next one. A plan's figures are `unknown` while its mode isn't running.

**Fast departure** can't be emptied, because Home Assistant's date-time entity has no empty value. A
departure already in the past means *charge now*.

## Service actions

These are for automations and scripts. They take their own fields, so nothing depends on the held
entities.

```yaml
# 80% by 7:00 tomorrow, low tariff only
action: gleanvolt.start_charging
data:
  mode: targeted
  target_soc: 80
  depart_by: "{{ (today_at('07:00') + timedelta(days=1)).isoformat() }}"
  low_tariff_only: true
```

```yaml
# What would it cost? Starts nothing and writes nothing to the charger.
action: gleanvolt.preview_targeted
data:
  target_soc: 80
  depart_by: "{{ (today_at('07:00') + timedelta(days=1)).isoformat() }}"
response_variable: quote
# quote.plan.gridEnergyWh, quote.plan.shortfallWh, quote.plan.reason …
```

| Action | Fields |
|---|---|
| `gleanvolt.start_charging` | `mode` (`solar`, `forecasted`, `solar_grid`, `fast_no_battery`, `targeted`). For a fast charge: `basis` (`full`, `energy`, `soc`), `energy_kwh`, `target_soc`, `depart_by`. For a targeted charge: `energy_kwh` or `target_soc`, `depart_by`, `priority` (`cheapest`, `just_in_time`), `rest_soc`, `sun_only`, `low_tariff_only`. Fails with Gleanvolt's reason when it refuses. |
| `gleanvolt.stop_charging` | None. |
| `gleanvolt.preview_targeted` | The targeted fields. Returns the plan as response data: the same answer as `POST /api/v1/plans/targeted/preview`. |

Each action also takes `config_entry_id`. You only need it with more than one Gleanvolt.

## Not in this release

- **Minimum battery SOC, SOC resume margin and min solar surplus.** The 1.2 API can't change them yet.
  Gleanvolt 1.3 adds them to the API ([#392](https://github.com/mpospisil/gleanvolt/issues/392)), and a
  later release of this integration uses them.
- **Push updates.** It polls: `/status` every 10 s; the car, the tariff and the two options every
  minute; `/health` every 5 minutes. It never asks for weather.
- **Settings, the tariff table, Solcast and the setup wizard.** These stay in the web UI.
- **Stopping the service.** The API doesn't do it, by design.

## Development

```bash
docker run --rm -v "$PWD":/w -w /w python:3.13 sh -c \
  "pip install -q -r requirements_test.txt ruff && ruff check . && ruff format --check . && pytest -q"
```

`contract/openapi.json` is the document a Gleanvolt 1.2.0 installation serves at
`/api/v1/openapi.json`. `tests/test_contract.py` checks that every route, every field the entities read
and every field the integration sends exists in it. Refresh the contract when you raise the minimum
version.

**Releasing:** set `version` in `custom_components/gleanvolt/manifest.json` and push a tag
`v<that version>`. The release workflow checks that the two match and publishes a GitHub release,
which HACS offers as an update.

## License

MIT
