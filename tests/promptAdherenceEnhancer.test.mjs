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
        get rootGraph() {
            throw new Error("The extension must use the active canvas graph, not a root-graph accessor.");
        },
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
    const rectangles = [];
    return {
        drawnText,
        rectangles,
        save() {},
        restore() {},
        fillRect(...args) { rectangles.push(args); },
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

test("Classic LiteGraph reserves a minimum-height strip for model info during resize", async () => {
    const { node } = await makeRegisteredNode(false);
    const baseSize = node._paaBaseComputeSize();
    const minimum = node.computeSize();

    assert.equal(minimum[0], 360);
    assert.equal(minimum[1], baseSize[1] + 78);

    // LiteGraph clamps a resize request against node.computeSize(). This
    // simulates dragging the resize handle below the minimum height.
    const requestedShortHeight = minimum[1] - 40;
    node.setSize([minimum[0], Math.max(requestedShortHeight, minimum[1])]);
    assert.equal(node.size[1], minimum[1]);

    node.onExecuted({
        detected_model: ["Anima"],
        detection_details: ["Class: FakeAnima | Adapter: post-LLM-adapter text-context scaling"],
    });

    const context = makeCanvasContext();
    node.onDrawForeground(context);
    assert.equal(context.rectangles.length, 1);
    assert.equal(context.rectangles[0][1], baseSize[1] + 4);
    assert.equal(context.rectangles[0][3], 70);

    // Growing the node must not move the fixed information panel over or
    // away from the controls; it stays immediately below the measured widgets.
    node.setSize([minimum[0], minimum[1] + 120]);
    const largerContext = makeCanvasContext();
    node.onDrawForeground(largerContext);
    assert.equal(largerContext.rectangles[0][1], baseSize[1] + 4);
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
    app.canvas.graph = { _nodes: [node] };

    await state.extension.setup();
    const onModeChange = settingListeners.get("Comfy.VueNodes.Enabled.change");
    assert.equal(typeof onModeChange, "function");

    mode.vue = true;
    onModeChange();
    assert.deepEqual(Array.from(node.widgets, (widget) => widget.name), [MODEL_WIDGET, DETAILS_WIDGET]);

    mode.vue = false;
    onModeChange();
    assert.equal(node.widgets.length, 0);
    assert.deepEqual(Array.from(node.size), [460, 198]);
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
