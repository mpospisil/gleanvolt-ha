// The Gleanvolt panel and card, in two sections.
//
// 1. PV status: what the roof, the grid and the home battery are doing, and the forecast.
// 2. Charging: what is charging now. While Gleanvolt drives the charger (any mode but Off), only that
//    mode's figures and Stop show: the mode can't be changed and nothing can be edited. While it is
//    Off, "Mode to start" picks a mode, its settings show, and Start starts it, like the web UI's tabs.
//
// Loaded by the integration itself (panel.py): the sidebar gets a Gleanvolt panel, and the card picker
// a Gleanvolt card that needs no configuration. Entities are found by the integration's own keys
// (translation_key), not by entity id, so renames, an area prefix or a Czech Home Assistant don't
// matter. The rendering is Home Assistant's own entities, conditional and vertical-stack cards.

// LAYOUT-BEGIN (tests/test_panel.py checks every "domain.key" here is an entity the integration makes)
const LAYOUT = {
  "pv": [
    "sensor.solar_power",
    "sensor.forecast_solar_power",
    "sensor.forecast_today",
    "sensor.forecast_still_to_come",
    "sensor.tomorrow_forecast",
    "sensor.grid_power",
    "binary_sensor.low_tariff",
    "sensor.grid_price",
    "sensor.battery_soc",
    "sensor.battery_power",
    "switch.battery_discharge_hold"
  ],
  "charging": [
    "sensor.charge_mode",
    "sensor.control_state",
    "sensor.charger_status",
    "binary_sensor.car_connected",
    "sensor.car_soc",
    "sensor.ev_charging_power",
    "sensor.session_energy"
  ],
  "mode": "sensor.charge_mode",
  "picker": "select.mode_to_start",
  "start": "button.start_mode",
  "stop": "button.stop_charging",
  "modes": {
    "solar": {
      "setup": [],
      "running": [
        "sensor.solar_surplus",
        "sensor.target_charging_current"
      ]
    },
    "forecasted": {
      "setup": [
        "switch.forecasted_until_full"
      ],
      "running": [
        "sensor.plan_state",
        "sensor.ev_energy_budget",
        "sensor.required_soc_floor",
        "sensor.projected_shortfall",
        "sensor.forecast_remaining_today",
        "sensor.battery_loan_power",
        "sensor.battery_loaned_today"
      ]
    },
    "solar_grid": {
      "setup": [
        "switch.solar_grid_low_tariff_only"
      ],
      "running": [
        "sensor.solar_surplus",
        "sensor.target_charging_current"
      ]
    },
    "fast_no_battery": {
      "setup": [
        "select.fast_basis",
        { "entity": "number.fast_energy", "when": ["select.fast_basis", "energy"] },
        { "entity": "number.fast_target_soc", "when": ["select.fast_basis", "soc"] },
        "datetime.fast_departure",
        "switch.fast_low_tariff_only"
      ],
      "running": [
        "sensor.fast_delivered",
        "sensor.fast_target",
        "sensor.fast_start"
      ]
    },
    "targeted": {
      "setup": [
        "sensor.car_range",
        "select.target_basis",
        { "entity": "number.target_energy", "when": ["select.target_basis", "energy"] },
        { "entity": "number.target_soc", "when": ["select.target_basis", "soc"] },
        "datetime.departure",
        "select.charge_priority",
        { "entity": "number.target_rest_soc", "when": ["select.charge_priority", "just_in_time"] },
        "switch.target_sun_only",
        "switch.target_low_tariff_only"
      ],
      "running": [
        "sensor.target_plan_state",
        "sensor.target_solar_energy",
        "sensor.target_grid_energy",
        "sensor.target_expected",
        "sensor.target_shortfall",
        "sensor.charging_from",
        "sensor.target_hold_until"
      ]
    }
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
    pv: "PV status",
    charging: "Charging",
    running: (mode) => `${mode} is charging`,
    setup: (mode) => `${mode}: settings`,
    start: (mode) => `Start ${mode}`,
    none: "No Gleanvolt device. Add the Gleanvolt integration under Settings → Devices & services.",
    description: "PV status, and charging: the running mode, or the mode to start with its settings.",
  },
  cs: {
    pv: "Stav FVE",
    charging: "Nabíjení",
    running: (mode) => `Nabíjí ${mode}`,
    setup: (mode) => `${mode}: nastavení`,
    start: (mode) => `Spustit ${mode}`,
    none: "Žádné zařízení Gleanvolt. Přidejte integraci Gleanvolt v Nastavení → Zařízení a služby.",
    description: "Stav FVE a nabíjení: běžící režim, nebo režim ke spuštění s jeho nastavením.",
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

/** The entity's name without the device's in front: "Grid power", not "Jinacovice Grid power". */
function shortName(hass, entityId, device) {
  const state = hass.states[entityId];
  const name = state && state.attributes.friendly_name;
  if (!name) return undefined;
  return name.startsWith(`${device} `) ? name.slice(device.length + 1) : name;
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

/**
 * The card configurations for one installation, as three blocks laid out by width: PV status,
 * charging, and the mode card (the running mode's figures and Stop, or the mode to start).
 */
function buildConfig(hass, deviceId, showName) {
  const ids = entityMap(hass, deviceId);
  const t = text(hass);
  const device = deviceName(hass, deviceId);
  const row = (key, name) =>
    ids[key] ? { entity: ids[key], name: name || shortName(hass, ids[key], device) } : null;
  const rows = (items) =>
    items
      .map((item) => {
        if (typeof item === "string") return row(item);
        const inner = row(item.entity);
        const [whenKey, state] = item.when;
        return inner && ids[whenKey]
          ? { type: "conditional", conditions: [{ entity: ids[whenKey], state }], row: inner }
          : null;
      })
      .filter(Boolean);
  const titled = (title) => (showName ? `${device} · ${title}` : title);
  const whenMode = (state) => [{ condition: "state", entity: ids[LAYOUT.mode], state }];

  const pv = { type: "entities", title: titled(t.pv), state_color: true, entities: rows(LAYOUT.pv) };
  const status = {
    type: "entities",
    title: titled(t.charging),
    state_color: true,
    entities: rows(LAYOUT.charging),
  };
  const cards = [];

  if (ids[LAYOUT.mode]) {
    // Gleanvolt is charging: that mode's figures, and Stop. Nothing to change or edit.
    for (const [mode, parts] of Object.entries(LAYOUT.modes)) {
      const entities = rows(parts.running);
      const stop = row(LAYOUT.stop);
      if (stop) entities.push(stop);
      cards.push({
        type: "conditional",
        conditions: whenMode(mode),
        card: { type: "entities", title: t.running(MODE_NAMES[mode]), state_color: true, entities },
      });
    }

    // Off: pick a mode, set what it needs, start it.
    const picker = ids[LAYOUT.picker];
    if (picker) {
      cards.push({
        type: "conditional",
        conditions: whenMode("off"),
        card: { type: "entities", entities: [row(LAYOUT.picker)] },
      });
      for (const [mode, parts] of Object.entries(LAYOUT.modes)) {
        const entities = rows(parts.setup);
        const start = row(LAYOUT.start, t.start(MODE_NAMES[mode]));
        if (start) entities.push(start);
        cards.push({
          type: "conditional",
          conditions: [...whenMode("off"), { condition: "state", entity: picker, state: mode }],
          card: { type: "entities", title: t.setup(MODE_NAMES[mode]), state_color: true, entities },
        });
      }
    }
  }
  return { pv, status, mode: { type: "vertical-stack", cards } };
}

// One column on a phone; PV status beside charging from 760 px; three columns from 1150 px. Container
// queries, so the card follows the width it is given: the whole panel, or one dashboard column.
const STYLE = `
  :host { display: block; container-type: inline-size; }
  .grid { display: grid; gap: var(--ha-section-grid-row-gap, 8px) 16px; align-items: start;
    grid-template-columns: minmax(0, 1fr); grid-template-areas: "pv" "status" "mode"; }
  .pv { grid-area: pv; } .status { grid-area: status; } .mode { grid-area: mode; }
  .mode:empty { display: none; }
  @container (min-width: 760px) {
    .grid { grid-template-columns: repeat(2, minmax(0, 1fr)); grid-template-areas: "pv status" "pv mode"; }
  }
  @container (min-width: 1150px) {
    .grid { grid-template-columns: repeat(3, minmax(0, 1fr)); grid-template-areas: "pv status mode"; }
  }
`;
const BLOCKS = ["pv", "status", "mode"];

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
    if (!this._root) {
      this._root = this.attachShadow({ mode: "open" });
      this._root.innerHTML = `<style>${STYLE}</style><div class="grid"></div>`;
      this._grid = this._root.querySelector(".grid");
      this._cards = [];
    }
    const deviceId = (this._config && this._config.device_id) || gleanvoltDevices(hass)[0];
    if (!deviceId) {
      if (this._signature !== "none") {
        this._signature = "none";
        this._message(text(hass).none);
      }
      return;
    }
    const config = buildConfig(hass, deviceId, Boolean(this._config && this._config.show_name));
    const signature = JSON.stringify(config);
    if (signature !== this._signature && !this._building) {
      // Rebuilt only when the entities, their names or the language change; otherwise just fed the
      // new state, and the conditional cards switch between charging and the mode to start.
      this._building = true;
      try {
        const helpers = await cardHelpers();
        this._grid.innerHTML = "";
        this._cards = BLOCKS.map((block) => {
          const holder = document.createElement("div");
          holder.className = block;
          const card = helpers.createCardElement(config[block]);
          holder.appendChild(card);
          this._grid.appendChild(holder);
          return card;
        });
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
    for (const card of this._cards) card.hass = this._hass;
  }

  _message(message) {
    this._grid.innerHTML = "";
    const card = document.createElement("ha-card");
    card.style.display = "block";
    card.style.padding = "16px";
    card.textContent = message;
    this._grid.appendChild(card);
    this._cards = [];
  }

  getCardSize() {
    return 14;
  }

  static getStubConfig() {
    return {};
  }
}

/**
 * The sidebar panel: one Gleanvolt card per installation, one under another and each the full
 * width, so the card can spread into columns. Named when there is more than one.
 */
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
          .cards { display: flex; flex-direction: column; gap: 24px; padding: 16px;
            max-width: 1800px; margin: 0 auto; }
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
    const showName = devices.length > 1;
    for (const [id, card] of this._byDevice) {
      if (!wanted.includes(id)) {
        card.remove();
        this._byDevice.delete(id);
      }
    }
    for (const id of wanted) {
      let card = this._byDevice.get(id);
      if (!card || card._showName !== showName) {
        if (card) card.remove();
        card = document.createElement("gleanvolt-card");
        card.setConfig(id ? { device_id: id, show_name: showName } : {});
        card._showName = showName;
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
