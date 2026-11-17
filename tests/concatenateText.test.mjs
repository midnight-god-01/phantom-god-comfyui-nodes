import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { runInNewContext } from "node:vm";
import test from "node:test";

const source = await readFile(new URL("../web/js/concatenateText.js", import.meta.url), "utf8");

function loadExtension() {
    const script = source
        .replace('import { app } from "../../scripts/app.js";\n', "")
        .replace('import { ComfyWidgets } from "../../scripts/widgets.js";\n', "");
    assert.notEqual(script, source, "expected to remove frontend imports");

    const extensions = [];
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

    runInNewContext(script, { app, ComfyWidgets, console: { info() {}, error() {} } });
    assert.equal(extensions.length, 1);
    return extensions[0];
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
            { name: "delimiter", value: " " },
            { name: "text_1", value: "first" },
            { name: "text_2", value: "second" },
        ],
        inputs: [
            { name: "text_1", type: "STRING", widget: { name: "text_1" } },
            { name: "text_2", type: "STRING", widget: { name: "text_2" } },
        ],
        addWidget(type, name, value, callback, options = {}) {
            const widget = { type, name, value, callback, options };
            this.widgets.push(widget);
            return widget;
        },
        addInput(name, type, options) {
            const input = { name, type, link: null, ...options };
            this.inputs.push(input);
            return input;
        },
        computeSize() { return [420, 300]; },
        setSize(size) { this.size = size; },
        setDirtyCanvas() {},
    });
    return node;
}

test("registers the Concatenate Text frontend feature", () => {
    const extension = loadExtension();
    assert.equal(extension.name, "PhantomGod.ConcatenateText");
});

test("adds unlimited multiline text fields with STRING sockets", () => {
    const extension = loadExtension();
    const NodeType = makeNodeType();
    extension.beforeRegisterNodeDef(NodeType, { name: "PhantomGodConcatenateText" });
    const node = makeNode(NodeType);
    node.onNodeCreated();

    const addButton = node.widgets.find((widget) => widget.name === "Add Text");
    assert.ok(addButton);
    assert.equal(addButton.serialize, false);
    addButton.callback();
    addButton.callback();

    assert.deepEqual(
        node.widgets.filter((widget) => widget.name.startsWith("text_")).map((widget) => widget.name),
        ["text_1", "text_2", "text_3", "text_4"],
    );
    assert.deepEqual(
        node.inputs.map((input) => input.name),
        ["text_1", "text_2", "text_3", "text_4"],
    );
    assert.equal(node.widgets.find((widget) => widget.name === "text_3").options.multiline, true);
    assert.equal(node.widgets.at(-1).name, "Add Text");
    assert.ok(node.inputs.find((input) => input.name === "text_4").widget);
});

test("restores dynamic fields and widget values from a saved workflow", () => {
    const extension = loadExtension();
    const NodeType = makeNodeType();
    extension.beforeRegisterNodeDef(NodeType, { name: "PhantomGodConcatenateText" });
    const node = makeNode(NodeType);
    node.onNodeCreated();

    const workflowNode = {
        inputs: [
            { name: "text_1", type: "STRING", widget: { name: "text_1" } },
            { name: "text_2", type: "STRING", widget: { name: "text_2" } },
            { name: "text_3", type: "STRING", widget: { name: "text_3" } },
            { name: "text_4", type: "STRING", widget: { name: "text_4" } },
        ],
        widgets_values: [" ", "alpha", "beta", "old-gamma", "old-delta"],
        widgets_values_named: {
            delimiter: " ",
            text_1: "alpha",
            text_2: "beta",
            text_3: "gamma",
            text_4: "delta",
        },
    };

    node.inputs = workflowNode.inputs.map((input) => ({ ...input }));
    node.widgets[0].value = workflowNode.widgets_values[0];
    node.widgets[1].value = workflowNode.widgets_values[1];
    node.widgets[2].value = workflowNode.widgets_values[2];
    node.widgets.at(-1).value = "incorrect-restored-button-label";
    node.onConfigure(workflowNode);

    assert.equal(node.widgets.find((widget) => widget.name === "text_3").value, "gamma");
    assert.equal(node.widgets.find((widget) => widget.name === "text_4").value, "delta");
    assert.equal(node.widgets.at(-1).value, "Add Text");
    assert.ok(node.inputs.find((input) => input.name === "text_4").widget);
    assert.equal(node.widgets.at(-1).name, "Add Text");
});

test("does not patch unrelated node definitions", () => {
    const extension = loadExtension();
    const NodeType = makeNodeType();
    extension.beforeRegisterNodeDef(NodeType, { name: "OtherNode" });
    const node = makeNode(NodeType);
    node.onNodeCreated();
    assert.equal(node.widgets.some((widget) => widget.name === "Add Text"), false);
});

test("restores older workflows that only contain positional widget values", () => {
    const extension = loadExtension();
    const NodeType = makeNodeType();
    extension.beforeRegisterNodeDef(NodeType, { name: "PhantomGodConcatenateText" });
    const node = makeNode(NodeType);
    node.onNodeCreated();

    const workflowNode = {
        inputs: [
            { name: "text_1", type: "STRING", widget: { name: "text_1" } },
            { name: "text_2", type: "STRING", widget: { name: "text_2" } },
            { name: "text_3", type: "STRING", widget: { name: "text_3" } },
        ],
        widgets_values: [" ", "one", "two", "three"],
    };
    node.inputs = workflowNode.inputs.map((input) => ({ ...input }));
    node.onConfigure(workflowNode);

    assert.equal(node.widgets.find((widget) => widget.name === "text_3").value, "three");
    assert.equal(node.widgets.at(-1).value, "Add Text");
});
