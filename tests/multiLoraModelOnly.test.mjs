import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { runInNewContext } from "node:vm";
import test from "node:test";

const source = await readFile(new URL("../web/js/multiLoraModelOnly.js", import.meta.url), "utf8");

class FakeElement {
    constructor(tagName) {
        this.tagName = tagName;
        this.children = [];
        this.listeners = {};
        this.dataset = {};
        this.style = {};
        this.className = "";
        this.textContent = "";
        this.value = "";
        this.title = "";
        this.attributes = {};
        this.disabled = false;
    }

    appendChild(child) {
        this.children.push(child);
        return child;
    }

    addEventListener(name, callback) {
        (this.listeners[name] ??= []).push(callback);
    }

    setAttribute(name, value) {
        this.attributes[name] = value;
    }

    set innerHTML(value) {
        if (value === "") this.children = [];
        this._innerHTML = value;
    }

    get innerHTML() {
        return this._innerHTML ?? "";
    }

    dispatch(name) {
        for (const callback of this.listeners[name] ?? []) {
            callback({ preventDefault() {}, stopPropagation() {} });
        }
    }

    click() {
        this.dispatch("click");
    }

    remove() {
        this.removed = true;
    }
}

function makeDocument() {
    const ids = new Map();
    const head = new FakeElement("head");
    const append = head.appendChild.bind(head);
    head.appendChild = (child) => {
        if (child.id) ids.set(child.id, child);
        return append(child);
    };
    return {
        head,
        createElement: (tag) => new FakeElement(tag),
        getElementById: (id) => ids.get(id) ?? null,
    };
}

function loadExtension() {
    const script = source
        .replace('import { app } from "../../scripts/app.js";\n', "")
        .replace('import { api } from "../../scripts/api.js";\n', "");
    assert.notEqual(script, source, "expected to remove frontend imports");

    const extensions = [];
    const document = makeDocument();
    const app = {
        graph: null,
        async graphToPrompt() {
            return {
                output: {
                    "1": {
                        class_type: "PhantomGodMultiLoraModelOnly",
                        inputs: { model: ["base", 0] },
                    },
                },
            };
        },
        registerExtension(extension) { extensions.push(extension); },
    };
    const api = {
        async fetchApi(route) {
            assert.equal(route, "/models/loras");
            return {
                ok: true,
                status: 200,
                async json() {
                    return ["style-a.safetensors", "style-b.safetensors"];
                },
            };
        },
    };

    runInNewContext(script, {
        app,
        api,
        document,
        window: { LiteGraph: { vueNodesMode: false } },
        console: { info() {}, warn() {} },
    });
    assert.equal(extensions.length, 1);
    return { extension: extensions[0], app, document };
}

function makeNode() {
    return {
        id: 1,
        type: "PhantomGodMultiLoraModelOnly",
        comfyClass: "PhantomGodMultiLoraModelOnly",
        properties: {},
        widgets: [],
        size: [320, 100],
        graph: { change() {}, incrementVersion() {} },
        addDOMWidget(name, type, element, options) {
            const widget = { name, type, element, options };
            this.widgets.push(widget);
            return widget;
        },
        computeSize() { return [360, 220]; },
        setSize(size) { this.size = size; },
        setDirtyCanvas() {},
    };
}

async function flushPromises() {
    await Promise.resolve();
    await Promise.resolve();
    await new Promise((resolve) => setTimeout(resolve, 0));
}

function readRows(node) {
    return JSON.parse(node.properties.phantomGodModelLoraState || '{"loras":[]}').loras;
}

test("registers a model-only multi-LoRA frontend extension", () => {
    const { extension } = loadExtension();
    assert.equal(extension.name, "PhantomGod.MultiLoraModelOnly");
});

test("adds multiple independent LoRA rows with file and strength controls", async () => {
    const { extension, app } = loadExtension();
    const node = makeNode();
    app.graph = { _nodes: [node], setDirtyCanvas() {} };
    // Simulate the serialized JSON STRING widget that Vue can otherwise display.
    node.widgets.push({
        name: "LoraStackState",
        value: "{}",
        options: {},
        computeSize() { return [320, 60]; },
        element: { style: {} },
    });
    extension.nodeCreated(node);
    await flushPromises();

    const hiddenState = node.widgets.find((widget) => widget.name === "LoraStackState");
    assert.equal(hiddenState.hidden, true);
    assert.deepEqual(Array.from(hiddenState.computeSize()), [0, -4]);
    assert.equal(hiddenState.options.canvasOnly, true);

    const root = node.__phantomGodLoraRoot;
    const addButton = root.children[0].children[0];
    addButton.click();
    root.children[0].children[0].click();

    let rows = readRows(node);
    assert.equal(rows.length, 2);
    assert.deepEqual(rows.map((row) => row.on), [true, true]);

    const first = root.children[1].children[0];
    const second = root.children[1].children[1];
    first.children[0].value = "style-a.safetensors";
    first.children[0].dispatch("change");
    first.children[1].value = "0.75";
    first.children[1].dispatch("change");
    second.children[0].value = "style-b.safetensors";
    second.children[0].dispatch("change");

    rows = readRows(node);
    assert.equal(rows[0].name, "style-a.safetensors");
    assert.equal(rows[0].strength, 0.75);
    assert.equal(rows[1].name, "style-b.safetensors");

    // Each row has its own on/off control.
    root.children[1].children[0].children[2].click();
    rows = readRows(node);
    assert.equal(rows[0].on, false);
    assert.equal(rows[1].on, true);
});

test("supports more than the previous 64 LoRA rows", async () => {
    const { extension, app } = loadExtension();
    const node = makeNode();
    app.graph = { _nodes: [node], setDirtyCanvas() {} };
    extension.nodeCreated(node);
    await flushPromises();

    const root = node.__phantomGodLoraRoot;
    for (let i = 0; i < 70; i += 1) {
        root.children[0].children[0].click();
    }
    assert.equal(readRows(node).length, 70);
    assert.equal(root.children[0].children[2].textContent, "70 ACTIVE ROWS");
});

test("LoRA responsive rows remain fluid in narrow and wide nodes", async () => {
    const { extension, app, document } = loadExtension();
    const node = makeNode();
    app.graph = { _nodes: [node], setDirtyCanvas() {} };
    extension.nodeCreated(node);
    await flushPromises();

    const css = document.getElementById("phantom-god-multi-lora-style").textContent;
    assert.match(css, /grid-template-columns:minmax\(0,1fr\) minmax\(54px,72px\) 44px 28px/);
    assert.match(css, /width:100%;min-width:0/);
});

test("injects row state into the hidden ComfyUI prompt input", async () => {
    const { extension, app } = loadExtension();
    const node = makeNode();
    app.graph = { _nodes: [node], setDirtyCanvas() {} };
    extension.nodeCreated(node);
    await flushPromises();

    node.__phantomGodLoraRoot.children[0].children[0].click();
    const row = node.__phantomGodLoraRoot.children[1].children[0];
    row.children[0].value = "style-a.safetensors";
    row.children[0].dispatch("change");

    const prompt = await app.graphToPrompt();
    const hidden = JSON.parse(prompt.output["1"].inputs.LoraStackState);
    assert.deepEqual(hidden.loras, [
        { name: "style-a.safetensors", on: true, strength: 1 },
    ]);
});

test("removes an individual LoRA row, including an empty row", async () => {
    const { extension, app } = loadExtension();
    const node = makeNode();
    app.graph = { _nodes: [node], setDirtyCanvas() {} };
    extension.nodeCreated(node);
    await flushPromises();

    const root = node.__phantomGodLoraRoot;
    root.children[0].children[0].click();
    root.children[0].children[0].click();
    assert.equal(readRows(node).length, 2);

    // Delete the first row without choosing a file.
    root.children[1].children[0].children[3].click();
    assert.equal(readRows(node).length, 1);
    root.children[1].children[0].children[3].click();
    assert.equal(readRows(node).length, 0);
    assert.match(root.children[1].children[0].textContent, /No LoRAs added/);
});
