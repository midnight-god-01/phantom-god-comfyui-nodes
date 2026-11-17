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

    click() {
        for (const callback of this.listeners.click ?? []) {
            callback({ preventDefault() {}, stopPropagation() {} });
        }
    }

    remove() {
        this.removed = true;
    }
}

function makeDocument() {
    const ids = new Map();
    const head = new FakeElement("head");
    const originalAppend = head.appendChild.bind(head);
    head.appendChild = (child) => {
        if (child.id) ids.set(child.id, child);
        return originalAppend(child);
    };
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
    assert.notEqual(script, source, "expected to remove frontend imports");

    const extensions = [];
    const document = makeDocument();
    const app = {
        graph: { setDirtyCanvas() {} },
        registerExtension(extension) { extensions.push(extension); },
    };
    const ComfyWidgets = {
        STRING(node, name, spec) {
            const widget = {
                name,
                type: "customtext",
                value: spec[1].default ?? "",
                options: { ...spec[1] },
            };
            node.widgets.push(widget);
            return { widget };
        },
    };

    runInNewContext(script, {
        app,
        ComfyWidgets,
        document,
        window: { LiteGraph: { vueNodesMode: false } },
        console: { info() {}, error() {} },
    });
    assert.equal(extensions.length, 1);
    return { extension: extensions[0], document };
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
        widgets: [
            { name: "delimiter", value: " ", options: {} },
            { name: "text_1", value: "first", options: {} },
            { name: "text_2", value: "second", options: {} },
        ],
        inputs: [
            { name: "text_1", type: "STRING", widget: { name: "text_1" } },
            { name: "text_2", type: "STRING", widget: { name: "text_2" } },
        ],
        addDOMWidget(name, type, element, options) {
            const widget = { name, type, element, options };
            this.widgets.push(widget);
            return widget;
        },
        addInput(name, type, options) {
            const input = { name, type, link: null, ...options };
            this.inputs.push(input);
            return input;
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
    const { extension, document } = loadExtension();
    const NodeType = makeNodeType();
    extension.beforeRegisterNodeDef(NodeType, { name: "PhantomGodConcatenateText" });
    const node = makeNode(NodeType);
    node.onNodeCreated();
    return { node, document, extension };
}

test("registers the Concatenate Text frontend feature", () => {
    const { extension } = loadExtension();
    assert.equal(extension.name, "PhantomGod.ConcatenateText");
});

test("Add Text is rounded and creates a field labelled Text 3", () => {
    const { node, document } = setupNode();
    const root = node.__phantomGodTextControlRoot;
    const addButton = root.children[0];
    assert.equal(addButton.textContent, "Add Text");
    assert.match(document.getElementById("phantom-god-text-controls-style").textContent, /border-radius:6px/);

    addButton.click();
    const text3 = node.widgets.find((widget) => widget.name === "text_3");
    assert.ok(text3);
    assert.equal(text3.options.placeholder, "Text 3");
    assert.equal(text3.label, "Text 3");
    assert.equal(node.inputs.find((input) => input.name === "text_3").label, "Text 3");
    assert.ok(node.inputs.find((input) => input.name === "text_3").widget);
});

test("removes a specific added field and either default field", () => {
    const { node } = setupNode();
    const root = node.__phantomGodTextControlRoot;

    root.children[0].click(); // add Text 3
    let remove3 = root.children[1].children.find((button) => button.dataset.textIndex === "3");
    assert.ok(remove3);
    remove3.click();
    assert.equal(node.inputs.some((input) => input.name === "text_3"), false);
    assert.equal(node.widgets.some((widget) => widget.name === "text_3"), false);
    assert.deepEqual(node.removedInputs, ["text_3"]);

    const remove1 = root.children[1].children.find((button) => button.dataset.textIndex === "1");
    assert.ok(remove1);
    remove1.click();
    assert.equal(node.inputs.some((input) => input.name === "text_1"), false);
    assert.equal(node.widgets.some((widget) => widget.name === "text_1"), false);
});

test("restores remaining fields and named workflow values after removal", () => {
    const { node } = setupNode();
    const workflowNode = {
        inputs: [
            { name: "text_2", type: "STRING", widget: { name: "text_2" } },
            { name: "text_4", type: "STRING", widget: { name: "text_4" } },
        ],
        widgets_values: [" ", "old-two", "old-four"],
        widgets_values_named: {
            delimiter: " ",
            text_2: "second",
            text_4: "fourth",
        },
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

test("does not patch unrelated node definitions", () => {
    const { extension } = loadExtension();
    const NodeType = makeNodeType();
    extension.beforeRegisterNodeDef(NodeType, { name: "OtherNode" });
    const node = makeNode(NodeType);
    node.onNodeCreated();
    assert.equal(node.widgets.some((widget) => widget.name === "text_controls"), false);
});
