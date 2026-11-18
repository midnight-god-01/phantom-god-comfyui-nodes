import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { runInNewContext } from "node:vm";
import test from "node:test";

const source = await readFile(new URL("../web/js/concatenateText.js", import.meta.url), "utf8");

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
        this.isConnected = true;
    }
    appendChild(child) { this.children.push(child); return child; }
    append(...children) { this.children.push(...children); }
    addEventListener(name, callback) { (this.listeners[name] ??= []).push(callback); }
    setAttribute(name, value) { this.attributes[name] = value; }
    set innerHTML(value) { if (value === "") this.children = []; this._innerHTML = value; }
    get innerHTML() { return this._innerHTML ?? ""; }
    replaceChildren(...children) { this.children = [...children]; }
    click() { for (const callback of this.listeners.click ?? []) callback({ preventDefault() {}, stopPropagation() {} }); }
    remove() { this.removed = true; this.isConnected = false; }
}

function makeDocument() {
    const ids = new Map();
    const head = new FakeElement("head");
    const append = head.appendChild.bind(head);
    head.appendChild = (child) => { if (child.id) ids.set(child.id, child); return append(child); };
    return {
        head,
        createElement: (tagName) => new FakeElement(tagName),
        getElementById: (id) => ids.get(id) ?? null,
    };
}

function loadExtension() {
    const script = source
        .replace('import { app } from "../../scripts/app.js";\n', "")
        .replace('import { ComfyWidgets } from "../../scripts/widgets.js";\n', "");
    assert.notEqual(script, source);
    const extensions = [];
    const document = makeDocument();
    const app = {
        graph: { _nodes: [], setDirtyCanvas() {} },
        async graphToPrompt() {
            return {
                output: {
                    "1": {
                        class_type: "PhantomGodConcatenateText",
                        inputs: { text_1: "first", text_2: "second" },
                    },
                },
            };
        },
        registerExtension(extension) { extensions.push(extension); },
    };
    const ComfyWidgets = {
        STRING(node, name, spec) {
            const widget = {
                name, type: "customtext", value: spec[1].default ?? "", options: { ...spec[1] },
            };
            node.widgets.push(widget);
            return { widget };
        },
    };
    runInNewContext(script, {
        app, ComfyWidgets, document,
        window: { LiteGraph: { vueNodesMode: false } },
        console: { info() {}, error() {} },
    });
    return { extension: extensions[0], document, app };
}

function makeNodeType() {
    return class MockConcatenateNode {
        onNodeCreated() {}
        onConfigure() {}
    };
}

function makeNode(NodeType = makeNodeType()) {
    const node = new NodeType();
    Object.assign(node, {
        type: "PhantomGodConcatenateText",
        comfyClass: "PhantomGodConcatenateText",
        properties: {},
        size: [420, 300],
        id: 1,
        widgets: [
            { name: "delimiter", value: " ", options: {} },
            { name: "text_1", value: "first", options: {}, computeSize(width) { return [width, 120]; } },
            { name: "text_2", value: "second", options: {}, computeSize(width) { return [width, 120]; } },
        ],
        inputs: [
            { name: "text_1", type: "STRING", widget: { name: "text_1" } },
            { name: "text_2", type: "STRING", widget: { name: "text_2" } },
        ],
        addDOMWidget(name, type, element, options) {
            const widget = { name, type, element, options };
            this.widgets.push(widget); return widget;
        },
        addInput(name, type, options) {
            const input = { name, type, link: null, ...options };
            this.inputs.push(input); return input;
        },
        removeInput(index) {
            this.removedInputs ??= [];
            this.removedInputs.push(this.inputs[index]?.name);
            this.inputs.splice(index, 1);
        },
        computeSize() { return [420, 300]; },
        setSize(size) { this.size = size; },
        setDirtyCanvas() {},
    });
    return node;
}

function setupNode() {
    const { extension, document, app } = loadExtension();
    const NodeType = makeNodeType();
    extension.beforeRegisterNodeDef(NodeType, { name: "PhantomGodConcatenateText" });
    const node = makeNode(NodeType);
    node.onNodeCreated();
    app.graph._nodes = [node];
    return { node, document, app };
}

test("registers the Concatenate Text frontend feature", () => {
    const { extension } = loadExtension();
    assert.equal(extension.name, "PhantomGod.ConcatenateText");
});

test("Add Text creates a field and each field has an individual toggle", () => {
    const { node, document } = setupNode();
    const root = node.__phantomGodTextControlRoot;
    assert.match(document.getElementById("phantom-god-text-controls-style").textContent, /grid-template-columns:minmax\(0,1fr\) 48px 28px/);
    // The native multiline widget must keep ComfyUI's own height calculation.
    assert.equal(node.widgets.find((widget) => widget.name === "text_1").computeSize(420)[1], 120);
    root.children[2].children[0].click();
    const text3 = node.widgets.find((widget) => widget.name === "text_3");
    assert.ok(text3);
    assert.equal(text3.options.placeholder, "Text 3");
    const field = root.children[1].children[2];
    assert.equal(field.children[0].textContent, "TEXT 3");
    assert.equal(field.children[1].textContent, "ON");
    field.children[1].click();
    assert.equal(node.properties.phantomGodTextRemoveState["3"], true);
    assert.equal(node.widgets.find((widget) => widget.name === "text_3").disabled, true);
    assert.equal(node.__phantomGodTextControlRoot.children[1].children[2].children[1].textContent, "OFF");
    node.__phantomGodTextControlRoot.children[1].children[2].children[1].click();
    assert.equal(node.properties.phantomGodTextRemoveState["3"], undefined);
});

test("OFF toggles exclude text fields from workflow execution", async () => {
    const { node, app } = setupNode();
    const firstRow = node.__phantomGodTextControlRoot.children[1].children[0];
    firstRow.children[1].click();
    assert.equal(node.properties.phantomGodTextRemoveState["1"], true);

    const prompt = await app.graphToPrompt();
    assert.equal(prompt.output["1"].inputs.text_1, "");
    assert.equal(prompt.output["1"].inputs.text_2, "second");
});

test("remove button deletes only its matching field", () => {
    const { node } = setupNode();
    node.__phantomGodTextControlRoot.children[2].children[0].click();
    const row = node.__phantomGodTextControlRoot.children[1].children[2];
    row.children[2].click();
    assert.equal(node.inputs.some((input) => input.name === "text_3"), false);
    assert.equal(node.widgets.some((widget) => widget.name === "text_3"), false);
    assert.deepEqual(node.removedInputs, ["text_3"]);
});

test("restores remaining fields and named workflow values after removal", () => {
    const { node } = setupNode();
    const workflowNode = {
        inputs: [
            { name: "text_2", type: "STRING", widget: { name: "text_2" } },
            { name: "text_4", type: "STRING", widget: { name: "text_4" } },
        ],
        widgets_values: [" ", "old-two", "old-four"],
        widgets_values_named: { delimiter: " ", text_2: "second", text_4: "fourth" },
    };
    node.inputs = workflowNode.inputs.map((input) => ({ ...input }));
    node.onConfigure(workflowNode);
    assert.equal(node.widgets.some((widget) => widget.name === "text_1"), false);
    assert.equal(node.widgets.find((widget) => widget.name === "text_2").value, "second");
    assert.equal(node.widgets.find((widget) => widget.name === "text_4").value, "fourth");
    assert.equal(node.__phantomGodTextControlRoot.children[1].children.length, 2);
});

test("restores old positional workflow values for non-contiguous fields", () => {
    const { node } = setupNode();
    const workflowNode = {
        inputs: [
            { name: "text_1", type: "STRING", widget: { name: "text_1" } },
            { name: "text_3", type: "STRING", widget: { name: "text_3" } },
        ],
        widgets_values: [" ", "one", "three"],
    };
    node.inputs = workflowNode.inputs.map((input) => ({ ...input }));
    node.onConfigure(workflowNode);
    assert.equal(node.widgets.find((widget) => widget.name === "text_1").value, "one");
    assert.equal(node.widgets.find((widget) => widget.name === "text_3").value, "three");
});


test("prompt injection follows each repeated nested subgraph execution path", async () => {
    const { app } = loadExtension();
    const { node: innerNode } = setupNode();
    innerNode.id = 5;
    innerNode.properties.phantomGodTextRemoveState = { "1": true };

    const sharedDefinition = { _nodes: [innerNode] };
    const firstInstance = { id: 10, subgraph: sharedDefinition };
    const secondInstance = { id: 11, subgraph: sharedDefinition };
    app.graph = { _nodes: [firstInstance, secondInstance] };
    app.graphToPrompt = async () => ({
        output: {
            "10:5": {
                class_type: "PhantomGodConcatenateText",
                inputs: { text_1: "native-a" },
            },
            "11:5": {
                class_type: "PhantomGodConcatenateText",
                inputs: { text_1: "native-b" },
            },
        },
    });

    const prompt = await app.graphToPrompt();
    assert.equal(prompt.output["10:5"].inputs.text_1, "");
    assert.equal(prompt.output["11:5"].inputs.text_1, "");
});

test("prompt injection does not apply root node state to an unmatched nested ID", async () => {
    const { node, app } = setupNode();
    node.properties.phantomGodTextRemoveState = { "1": true };
    app.graphToPrompt = async () => ({
        output: {
            "999:1": {
                class_type: "PhantomGodConcatenateText",
                inputs: { text_1: "preserve-this" },
            },
        },
    });

    const prompt = await app.graphToPrompt();
    assert.equal(prompt.output["999:1"].inputs.text_1, "preserve-this");
});

test("removing a field marks the graph as changed for workflow persistence", () => {
    const { node } = setupNode();
    const changes = { changed: 0, versions: 0 };
    node.graph = {
        change() { changes.changed += 1; },
        incrementVersion() { changes.versions += 1; },
    };
    node.__phantomGodTextControlRoot.children[2].children[0].click();
    node.__phantomGodTextControlRoot.children[1].children[2].children[2].click();
    assert.equal(changes.changed, 1);
    assert.equal(changes.versions, 1);
});


test("does not patch unrelated node definitions", () => {
    const { extension } = loadExtension();
    const NodeType = makeNodeType();
    extension.beforeRegisterNodeDef(NodeType, { name: "OtherNode" });
    const node = makeNode(NodeType);
    node.onNodeCreated();
    assert.equal(node.widgets.some((widget) => widget.name === "text_controls"), false);
});
