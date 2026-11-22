import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { runInNewContext } from "node:vm";
import test from "node:test";

const source = await readFile(
    new URL("../web/js/prompt_adherence_enhancer_pro.js", import.meta.url),
    "utf8"
);
const entryImport = /^import\s+\{\s*app\s*\}\s+from\s+["']\.\.\/\.\.\/scripts\/app\.js["'];?\s*/m;
const NODE_NAME = "PromptAdherenceEnhancerPro";
const MODEL_WIDGET = "Auto-detected model";
const DETAILS_WIDGET = "Detection / adapter details";

function loadExtension(initialVueMode = false) {
    const script = source.replace(entryImport, "");
    assert.notEqual(script, source, "expected to find and replace the ComfyUI app import");

    const extensions = [];
    const settingListeners = new Map();
    const mode = { vue: initialVueMode };
    const dirtyCalls = [];
    const app = {
        ui: {
            settings: {
                getSettingValue(name) {
                    assert.equal(name, "Comfy.VueNodes.Enabled");
                    return mode.vue;
                },
                addEventListener(name, callback) {
                    settingListeners.set(name, callback);
                },
            },
        },
        canvas: {
            graph: null,
            setDirty(...args) { dirtyCalls.push(args); },
        },
        rootGraph: null,
        registerExtension(extension) { extensions.push(extension); },
    };

    runInNewContext(script, { app, console }, {
        filename: "prompt_adherence_enhancer_pro.js",
    });
    assert.equal(extensions.length, 1);
    return { extension: extensions[0], mode, settingListeners, app, dirtyCalls };
}

function makeNodeType() {
    function Node() {
        this.type = NODE_NAME;
        this.widgets = [];
        this.properties = {};
        this.size = [240, 120];
        this.graph = { setDirtyCanvas() {} };
    }

    Node.prototype.onNodeCreated = function () {
        this.originalCreated = true;
    };
    Node.prototype.onExecuted = function () {
        this.originalExecuted = true;
    };
    Node.prototype.onConfigure = function () {
        this.originalConfigured = true;
    };
    Node.prototype.onDrawForeground = function () {
        this.originalDrawn = true;
    };
    Node.prototype.computeSize = function () {
        return [240, 120];
    };
    Node.prototype.setSize = function (size) {
        this.size = size;
    };
    Node.prototype.setDirtyCanvas = function () {};
    Node.prototype.addWidget = function (type, name, value, callback, options) {
        const widget = { type, name, value, callback, options, disabled: false };
        this.widgets.push(widget);
        return widget;
    };
    Node.prototype.removeWidget = function (widget) {
        this.widgets = this.widgets.filter((candidate) => candidate !== widget);
    };

    return Node;
}

function makeCanvasContext() {
    const drawnText = [];
    return {
        drawnText,
        save() {},
        restore() {},
        fillRect() {},
        strokeRect() {},
        measureText(value) {
            return { width: String(value).length * 5 };
        },
        fillText(value) {
            drawnText.push(String(value));
        },
    };
}

async function makeRegisteredNode(vueMode = false) {
    const state = loadExtension(vueMode);
    const Node = makeNodeType();
    await state.extension.beforeRegisterNodeDef(Node, { name: NODE_NAME }, state.app);
    const node = new Node();
    node.onNodeCreated();
    return { ...state, Node, node };
}

test("Classic LiteGraph renders the detected model in its canvas panel", async () => {
    const { node } = await makeRegisteredNode(false);

    assert.equal(node.originalCreated, true);
    assert.equal(node.widgets.length, 0, "Classic mode should not rely on Vue-only display widgets");
    assert.deepEqual(Array.from(node.size), [360, 198], "Classic mode reserves canvas-panel space");

    node.onExecuted({
        detected_model: ["MOSS-Image"],
        detection_details: ["Class: FakeMoss | Adapter: text_embedder output scaling"],
    });

    const context = makeCanvasContext();
    node.onDrawForeground(context);

    assert.equal(node.originalExecuted, true);
    assert.equal(node.originalDrawn, true);
    assert.equal(node.properties.paa_detected_model, "MOSS-Image");
    assert.ok(context.drawnText.includes("AUTO-DETECTED MODEL"));
    assert.ok(context.drawnText.includes("MOSS-Image"));
    assert.ok(context.drawnText.some((line) => line.includes("text_embedder")));
});

test("Nodes 2.0 uses read-only widgets and receives execution output", async () => {
    const { node } = await makeRegisteredNode(true);

    assert.deepEqual(
        Array.from(node.widgets, (widget) => widget.name),
        [MODEL_WIDGET, DETAILS_WIDGET]
    );
    assert.ok(node.widgets.every((widget) => widget.disabled));
    assert.equal(node.size[0], 460);

    node.onExecuted({
        detected_model: ["Qwen-Image 2.1"],
        detection_details: ["Class: FakeQwen | Adapter: txt_in text-projection scaling"],
    });

    assert.equal(node.widgets[0].value, "Qwen-Image 2.1");
    assert.match(node.widgets[1].value, /txt_in/);
    assert.equal(node.properties.paa_detected_model, "Qwen-Image 2.1");

    const context = makeCanvasContext();
    node.onDrawForeground(context);
    assert.equal(context.drawnText.length, 0, "Vue mode must not draw a duplicate canvas panel");
});

test("switching renderer modes rebuilds the display without reloading the workflow", async () => {
    const state = await makeRegisteredNode(false);
    const { node, app, mode, settingListeners } = state;
    app.rootGraph = { _nodes: [node] };
    app.canvas.graph = app.rootGraph;

    await state.extension.setup();
    const onModeChange = settingListeners.get("Comfy.VueNodes.Enabled.change");
    assert.equal(typeof onModeChange, "function");

    mode.vue = true;
    onModeChange();
    assert.deepEqual(Array.from(node.widgets, (widget) => widget.name), [MODEL_WIDGET, DETAILS_WIDGET]);

    mode.vue = false;
    onModeChange();
    assert.equal(node.widgets.length, 0);
    assert.deepEqual(Array.from(node.size), [360, 198]);
    assert.ok(state.dirtyCalls.length > 0);
});

test("saved detection details are retained when Classic mode redraws the node", async () => {
    const { node } = await makeRegisteredNode(false);
    node.properties.paa_detected_model = "Z-Image";
    node.properties.paa_detection_details = "Class: NextDiT | Adapter: cap_embedder";

    node.onConfigure();
    const context = makeCanvasContext();
    node.onDrawForeground(context);

    assert.equal(node.originalConfigured, true);
    assert.ok(context.drawnText.includes("Z-Image"));
    assert.ok(context.drawnText.some((line) => line.includes("cap_embedder")));
});

test("the extension ignores unrelated node definitions", async () => {
    const state = loadExtension(false);
    const Node = makeNodeType();
    const original = Node.prototype.onNodeCreated;

    await state.extension.beforeRegisterNodeDef(Node, { name: "SomeOtherNode" }, state.app);

    assert.equal(Node.prototype.onNodeCreated, original);
});
