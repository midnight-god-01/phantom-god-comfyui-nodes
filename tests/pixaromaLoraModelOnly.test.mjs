import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const source = await readFile(new URL("../web/js/pixaromaLoraModelOnly.js", import.meta.url), "utf8");

test("the frontend defines no CLIP controls or custom hidden-input or prompt-patching dependency", () => {
  assert.doesNotMatch(source, /clip/i);
  assert.match(source, /PixaromaLoraModelOnly/);
  assert.match(source, /lora_state/);
  assert.doesNotMatch(source, /LoraLoaderState|graphToPrompt|promptHook/);
});

test("the node exposes one visible MODEL socket pair and a standard hidden STRING state widget", async () => {
  const python = await readFile(new URL("../features/pixaroma_lora_model_only.py", import.meta.url), "utf8");
  assert.match(python, /RETURN_TYPES\s*=\s*\("MODEL",\)/);
  assert.match(python, /RETURN_NAMES\s*=\s*\("MODEL",\)/);
  assert.match(python, /"lora_state":\s*\("STRING",\s*\{"default": "\{\}"\}\)/);
  assert.match(python, /load_lora_for_models\([\s\S]*?model, None,[\s\S]*?0\.0/);
  assert.match(python, /return \(model,\)/);
  assert.doesNotMatch(python, /"hidden"\s*:/);
  assert.doesNotMatch(python, /RETURN_TYPES\s*=.*STRING/);
  assert.doesNotMatch(python, /trigger-string output/i);
});

test("the hidden state widget stays in workflow and prompt serialization", () => {
  assert.match(source, /widget\.hidden\s*=\s*true/);
  assert.match(source, /widget\.serialize\s*=\s*true/);
  assert.match(source, /widget\.options\.hidden\s*=\s*true/);
  assert.match(source, /widget\.options\.serialize\s*=\s*true/);
  assert.match(source, /widget\.value\s*=\s*JSON\.stringify\(promptState\(readState\(node\)\)\)/);
  assert.match(source, /strength\.min\s*=\s*"-100"/);
  assert.match(source, /strength\.max\s*=\s*"100"/);
  assert.match(source, /syncStateWidget\(this\)/);
});

test("settings controls share the dark theme and orange accent styling", () => {
  assert.match(source, /\.pg-ll-panel input\[type=number\],\.pg-ll-panel select\{[^}]*background-color:#171717/s);
  assert.match(source, /\.pg-ll-panel select\{[^}]*appearance:none/s);
  assert.match(source, /\.pg-ll-panel input\[type=checkbox\]\{[^}]*accent-color:var\(--pg-accent\)/s);
  assert.match(source, /\.pg-ll-panel footer button\{[^}]*min-height:32px/s);
  assert.match(source, /\.pg-ll-panel footer button:hover\{/);
  assert.match(source, /\.pg-ll-panel footer \.primary\{[^}]*background:var\(--pg-accent\)/s);
});

test("the frontend includes Pixaroma-style stack, row actions, info and settings", () => {
  for (const token of [
    "＋ Add LoRA", "strength", "pg-ll-toggle", "pg-ll-info", "LoRA information",
    "LoRA Loader settings", "Move up", "Move down", "Duplicate", "Remove", "#f66744",
  ]) {
    assert.ok(source.includes(token), `expected frontend to include ${token}`);
  }
});

test("metadata panel consumes the backend JSON response rather than re-parsing a tensor file", () => {
  assert.match(source, /await response\.json\(\)/);
  assert.match(source, /result\.info/);
  assert.match(source, /phantom-god\/lora-info/);
  assert.doesNotMatch(source, /arrayBuffer\(\)/);
});

test("the frontend has no trigger-word input, output, selection UI, or separator setting", () => {
  assert.doesNotMatch(source, /trigger|custom\s+word|pg-ll-chip/i);
  assert.doesNotMatch(source, /state\.sep|row\.triggers|offerDeclaredTriggers/);
});

test("package, Python metadata and extension log use one release version", async () => {
  const packageJson = JSON.parse(await readFile(new URL("../package.json", import.meta.url), "utf8"));
  const pyproject = await readFile(new URL("../pyproject.toml", import.meta.url), "utf8");
  const graphArrange = await readFile(new URL("../web/js/graphArrange.js", import.meta.url), "utf8");
  assert.equal(packageJson.version, "1.6.3");
  assert.match(pyproject, /^version = "1\.6\.3"/m);
  assert.match(graphArrange, /VERSION\s*=\s*"1\.6\.3"/);
});

test("the state widget is hidden and receives persisted LoRA rows", async () => {
  const vm = await import("node:vm");
  const extensionImport = /^import\s+.*?;\s*\n/gm;
  const script = source.replace(extensionImport, "");
  const createdExtensions = [];
  const makeElement = () => ({
    className: "",
    style: { setProperty() {} },
    dataset: {},
    children: [],
    isConnected: true,
    append(...children) { this.children.push(...children); },
    replaceChildren(...children) { this.children = [...children]; },
    addEventListener() {},
    setAttribute() {},
    remove() { this.isConnected = false; },
    focus() {},
  });
  const graph = { _nodes: [] };
  const app = {
    configuringGraph: false,
    rootGraphOrUndefined: graph,
    get graph() { throw new Error("Deprecated app.graph must not be read"); },
    registerExtension(extension) { createdExtensions.push(extension); },
    ui: { settings: { getSettingValue: () => undefined } },
  };
  const context = {
    app,
    api: { fetchApi: async () => ({ ok: true, json: async () => ["style.safetensors"] }) },
    window: { LiteGraph: { vueNodesMode: false } },
    document: {
      getElementById: () => null,
      createElement: makeElement,
      createTextNode: text => ({ textContent: text }),
      addEventListener() {},
      head: { append() {} },
      body: { append() {} },
    },
    console: { warn() {}, error() {}, log() {} },
    innerWidth: 1200,
    innerHeight: 800,
    queueMicrotask(callback) { callback(); },
  };
  vm.runInNewContext(script, context, { filename: "pixaromaLoraModelOnly.js" });
  assert.equal(createdExtensions.length, 1);

  const state = {
    loras: [{ id: "row-1", name: "style.safetensors", on: true, strength: 0.75 }],
    cacheMode: "all",
  };
  const stateWidget = { name: "lora_state", value: "{}", options: {} };
  const node = {
    id: 12,
    type: "PixaromaLoraModelOnly",
    comfyClass: "PixaromaLoraModelOnly",
    properties: { pixaromaLoraModelOnlyState: JSON.stringify(state) },
    widgets: [stateWidget],
    graph,
    size: [340, 140],
    computeSize() { return [340, 220]; },
    setSize(size) { this.size = size; },
    addDOMWidget() { return { options: {} }; },
  };
  graph._nodes.push(node);

  const nodeType = { prototype: {} };
  createdExtensions[0].beforeRegisterNodeDef(nodeType, { name: "PixaromaLoraModelOnly" });
  createdExtensions[0].nodeCreated(node);
  assert.deepEqual(Array.from(node.size), [340, 220], "a new node should fit its DOM widget");
  assert.equal(stateWidget.hidden, true);
  assert.equal(stateWidget.serialize, true);
  assert.equal(stateWidget.options.hidden, true);
  assert.equal(stateWidget.options.serialize, true);
  assert.deepEqual(Array.from(stateWidget.computeSize()), [0, -4]);
  const serialized = JSON.parse(stateWidget.value);
  assert.equal(serialized.cacheMode, "all");
  assert.equal(serialized.loras[0].name, "style.safetensors");
  assert.equal(serialized.loras[0].strength, 0.75);

  const updated = { loras: [{ id: "row-1", name: "style.safetensors", on: true, strength: 0.9 }], cacheMode: "none" };
  node.properties.pixaromaLoraModelOnlyState = JSON.stringify(updated);
  nodeType.prototype.onConfigure.call(node);
  const updatedSerialized = JSON.parse(stateWidget.value);
  assert.equal(updatedSerialized.cacheMode, "none");
  assert.equal(updatedSerialized.loras[0].strength, 0.9);
});
