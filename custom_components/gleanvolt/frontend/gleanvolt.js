// The Gleanvolt panel and card: the web UI's Charging plan tabs, in Home Assistant.
//
// Pick a mode in "Mode to start", and only that mode's controls and figures show, with its Start
// button. Loaded by the integration itself (frontend.py), so nobody pastes YAML: the sidebar gets a
// Gleanvolt panel, and the card picker a Gleanvolt card that needs no configuration.
//
// Entities are found by the integration's own keys (their translation_key), not by entity id, so a
// renamed entity, an area prefix or a Home Assistant in Czech all work. The rendering is Home
// Assistant's own entities, conditional and vertical-stack cards.

// LAYOUT-BEGIN (tests/test_frontend.py checks every "domain.key" here is an entity the integration makes)
const LAYOUT = {
  "top": [
    "select.charge_mode",
    "sensor.control_state",
    "sensor.charger_status",
    "binary_sensor.car_connected",
    "switch.battery_discharge_hold",
    "button.stop_charging"
  ],
  "picker": "select.mode_to_start",
  "start": "button.start_mode",
  "modes": {
    "solar": [
      "sensor.solar_surplus",
      "sensor.battery_soc",
      "sensor.ev_charging_power",
      "sensor.target_charging_current"
    ],
    "forecasted": [
      "switch.forecasted_until_full",
      { "running": true },
      "sensor.plan_state",
      "sensor.ev_energy_budget",
      "sensor.required_soc_floor",
      "sensor.projected_shortfall",
      "sensor.forecast_remaining_today",
      "sensor.tomorrow_forecast",
      "sensor.battery_loaned_today"
    ],
    "solar_grid": [
      "switch.solar_grid_low_tariff_only",
      "sensor.solar_surplus",
      "sensor.grid_power",
      "sensor.target_charging_current"
    ],
    "fast_no_battery": [
      "select.fast_basis",
      { "entity": "number.fast_energy", "when": ["select.fast_basis", "energy"] },
      { "entity": "number.fast_target_soc", "when": ["select.fast_basis", "soc"] },
      "datetime.fast_departure",
      "switch.fast_low_tariff_only",
      "sensor.car_soc",
      { "running": true },
      "sensor.ev_charging_power",
      "sensor.fast_delivered",
      "sensor.fast_target",
      "sensor.fast_start"
    ],
    "targeted": [
      "sensor.car_soc",
      "sensor.car_range",
      "select.target_basis",
      { "entity": "number.target_energy", "when": ["select.target_basis", "energy"] },
      { "entity": "number.target_soc", "when": ["select.target_basis", "soc"] },
      "datetime.departure",
      "select.charge_priority",
      { "entity": "number.target_rest_soc", "when": ["select.charge_priority", "just_in_time"] },
      "switch.target_sun_only",
      "switch.target_low_tariff_only",
      { "running": true },
      "sensor.target_plan_state",
      "sensor.target_solar_energy",
      "sensor.target_grid_energy",
      "sensor.target_expected",
      "sensor.target_shortfall",
      "sensor.charging_from"
    ]
  }
};
// LAYOUT-END

// Mode names stay English in every language, as in the web UI.
const MODE_NAMES = {
  solar: "Solar",
  forecasted: "Forecasted",
  solar_grid: "SolarGrid",
  fast_no_battery: "FastNoBattery",
  targeted: "Targeted",
};

const TEXT = {
  en: {
    running: (mode) => `While ${mode} runs`,
    start: (mode) => `Start ${mode}`,
    none: "No Gleanvolt device. Add the Gleanvolt integration under Settings → Devices & services.",
    description: "Charge mode, and the controls of the mode to start, like the web UI's tabs.",
  },
  cs: {
    running: (mode) => `Když běží ${mode}`,
    start: (mode) => `Spustit ${mode}`,
    none: "Žádné zařízení Gleanvolt. Přidejte integraci Gleanvolt v Nastavení → Zařízení a služby.",
    description: "Režim nabíjení a ovládání režimu ke spuštění, jako záložky webového rozhraní.",
  },
};

const text = (hass) => TEXT[(hass && hass.language) || "en"] || TEXT.en;

/** The device ids of every Gleanvolt installation, in a stable order. */
function gleanvoltDevices(hass) {
  const ids = new Set();
  for (const entry of Object.values(hass.entities || {})) {
    if (entry.platform === "gleanvolt" && entry.device_id) {
      ids.add(entry.device_id);
    }
  }
  return [...ids].sort();
}

function deviceName(hass, deviceId) {
  const device = (hass.devices || {})[deviceId];
  return (device && (device.name_by_user || device.name)) || "Gleanvolt";
}

/** "select.charge_mode" -> the entity id the device has for it. */
function entityMap(hass, deviceId) {
  const map = {};
  for (const entry of Object.values(hass.entities || {})) {
    if (entry.platform === "gleanvolt" && entry.device_id === deviceId && entry.translation_key) {
      map[`${entry.entity_id.split(".")[0]}.${entry.translation_key}`] = entry.entity_id;
    }
  }
  return map;
}

/**
 * Home Assistant's card factory. It lives in the dashboards' code, which a page loads only once a
 * dashboard has been opened, so a panel opened straight after a refresh has to load it first: the
 * panel resolver knows how, and is asked for the "lovelace" panel's route without showing it.
 */
async function cardHelpers() {
  if (!window.loadCardHelpers) {
    await customElements.whenDefined("partial-panel-resolver");
    const resolver = document.createElement("partial-panel-resolver");
    const getRoutes = (resolver._getRoutes || resolver.getRoutes).bind(resolver);
    const routes = getRoutes([{ component_name: "lovelace", url_path: "gleanvolt-loader" }]);
    const route = routes && routes.routes && routes.routes["gleanvolt-loader"];
    if (route && route.load) await route.load();
    for (let i = 0; i < 50 && !window.loadCardHelpers; i++) {
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
  }
  if (!window.loadCardHelpers) throw new Error("Home Assistant's card helpers did not load");
  return window.loadCardHelpers();
}

/** The card configuration for one installation, built from Home Assistant's own cards. */
function buildConfig(hass, deviceId) {
  const ids = entityMap(hass, deviceId);
  const t = text(hass);
  const row = (key) => (ids[key] ? { entity: ids[key] } : null);
  const rows = (items, mode) =>
    items
      .map((item) => {
        if (typeof item === "string") return row(item);
        if (item.running) return { type: "section", label: t.running(MODE_NAMES[mode]) };
        const inner = row(item.entity);
        const [whenKey, state] = item.when;
        return inner && ids[whenKey]
          ? { type: "conditional", conditions: [{ entity: ids[whenKey], state }], row: inner }
          : null;
      })
      .filter(Boolean);

  const cards = [
    { type: "entities", title: deviceName(hass, deviceId), state_color: true, entities: rows(LAYOUT.top) },
  ];
  const picker = ids[LAYOUT.picker];
  const start = ids[LAYOUT.start];
  if (picker) {
    cards.push({ type: "entities", entities: [{ entity: picker }] });
    for (const [mode, items] of Object.entries(LAYOUT.modes)) {
      const entities = rows(items, mode);
      if (start) entities.push({ entity: start, name: t.start(MODE_NAMES[mode]) });
      cards.push({
        type: "conditional",
        conditions: [{ condition: "state", entity: picker, state: mode }],
        card: { type: "entities", title: MODE_NAMES[mode], state_color: true, entities },
      });
    }
  }
  return { type: "vertical-stack", cards };
}

/**
 * The Gleanvolt card. Optional `device_id` picks the installation when there is more than one;
 * without it, the first.
 */
class GleanvoltCard extends HTMLElement {
  setConfig(config) {
    this._config = config || {};
    this._signature = null;
  }

  set hass(hass) {
    this._hass = hass;
    this._update();
  }

  async _update() {
    const hass = this._hass;
    if (!hass) return;
    const deviceId = (this._config && this._config.device_id) || gleanvoltDevices(hass)[0];
    if (!deviceId) {
      if (this._signature !== "none") {
        this._signature = "none";
        this._message(text(hass).none);
      }
      return;
    }
    const config = buildConfig(hass, deviceId);
    const signature = JSON.stringify(config);
    if (signature !== this._signature && !this._building) {
      // Rebuilt only when the entities or the language change; otherwise just fed the new state.
      this._building = true;
      try {
        const helpers = await cardHelpers();
        const card = helpers.createCardElement(config);
        this.innerHTML = "";
        this.appendChild(card);
        this._card = card;
        this._signature = signature;
      } catch (err) {
        // Said on the page rather than left blank, so a failure can be reported.
        console.error("Gleanvolt card", err);
        this._signature = signature;
        this._message(`Gleanvolt: ${err && err.message ? err.message : err}`);
      } finally {
        this._building = false;
      }
    }
    if (this._card) this._card.hass = this._hass;
  }

  _message(message) {
    this.innerHTML = "";
    const card = document.createElement("ha-card");
    card.style.display = "block";
    card.style.padding = "16px";
    card.textContent = message;
    this.appendChild(card);
    this._card = null;
  }

  getCardSize() {
    return 10;
  }

  static getStubConfig() {
    return {};
  }
}

/** The sidebar panel: one Gleanvolt card per installation. */
class GleanvoltPanel extends HTMLElement {
  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  set narrow(narrow) {
    this._narrow = narrow;
    if (this._menu) this._menu.narrow = narrow;
  }

  set panel(panel) {
    this._panel = panel;
  }

  _render() {
    const hass = this._hass;
    if (!this._root) {
      this._root = this.attachShadow({ mode: "open" });
      this._root.innerHTML = `
        <style>
          :host { display: block; min-height: 100vh; background: var(--primary-background-color); }
          .toolbar { display: flex; align-items: center; height: var(--header-height, 56px);
            padding: 0 12px; background: var(--app-header-background-color, var(--primary-color));
            color: var(--app-header-text-color, var(--text-primary-color)); font-size: 20px; }
          .toolbar .title { margin-left: 12px; }
          .cards { display: flex; flex-wrap: wrap; gap: 16px; justify-content: center; padding: 16px; }
          .cards > * { flex: 1 1 360px; max-width: 520px; }
        </style>
        <div class="toolbar"><ha-menu-button></ha-menu-button><span class="title">Gleanvolt</span></div>
        <div class="cards"></div>`;
      this._menu = this._root.querySelector("ha-menu-button");
      this._cards = this._root.querySelector(".cards");
      this._byDevice = new Map();
    }
    this._menu.hass = hass;
    this._menu.narrow = this._narrow;

    const devices = gleanvoltDevices(hass);
    const wanted = devices.length ? devices : [null];
    for (const [id, card] of this._byDevice) {
      if (!wanted.includes(id)) {
        card.remove();
        this._byDevice.delete(id);
      }
    }
    for (const id of wanted) {
      let card = this._byDevice.get(id);
      if (!card) {
        card = document.createElement("gleanvolt-card");
        card.setConfig(id ? { device_id: id } : {});
        this._cards.appendChild(card);
        this._byDevice.set(id, card);
      }
      card.hass = hass;
    }
  }
}

if (!customElements.get("gleanvolt-card")) {
  customElements.define("gleanvolt-card", GleanvoltCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "gleanvolt-card",
    name: "Gleanvolt",
    description: TEXT.en.description,
    preview: true,
    documentationURL: "https://github.com/mpospisil/gleanvolt-ha",
  });
}
if (!customElements.get("gleanvolt-panel")) {
  customElements.define("gleanvolt-panel", GleanvoltPanel);
}
