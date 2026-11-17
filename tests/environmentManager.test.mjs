import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { runInNewContext } from "node:vm";
import test from "node:test";

const source = await readFile(new URL("../web/js/environmentManager.js", import.meta.url), "utf8");

class FakeElement {
    constructor(tagName) {
        this.tagName = tagName;
        this.children = [];
        this.listeners = {};
        this.style = {};
        this.className = "";
        this.textContent = "";
        this.disabled = false;
        this.offsetHeight = 0;
    }
    appendChild(child) { this.children.push(child); return child; }
    addEventListener(name, callback) { (this.listeners[name] ??= []).push(callback); }
    setAttribute(name, value) { (this.attributes ??= {})[name] = value; }
    replaceChildren(...children) { this.children = [...children]; }
    remove() { this.removed = true; }
    click() {
        for (const callback of this.listeners.click ?? []) {
            callback({ preventDefault() {}, stopPropagation() {} });
        }
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

function loadExtension(report) {
    const script = source
        .replace('import { app } from "../../scripts/app.js";\n', "")
        .replace('import { api } from "../../scripts/api.js";\n', "");
    assert.notEqual(script, source);

    const extensions = [];
    const document = makeDocument();
    const app = { graph: { setDirtyCanvas() {} }, registerExtension(ext) { extensions.push(ext); } };
    const api = {
        async fetchApi(route) {
            assert.equal(route, "/phantom_god/environment/check");
            return { ok: true, async json() { return report; } };
        },
    };
    runInNewContext(script, {
        app, api, document,
        window: { LiteGraph: { vueNodesMode: true } },
        console: { info() {}, warn() {}, error() {} },
    });
    return { extension: extensions[0], document };
}

function makeReport() {
    return {
        environment: {
            python: "3.13.14",
            python_executable: "C:/ComfyUI/python.exe",
            pip_available: true,
            pip_version: "25.0",
            torch: "2.14.1+cu130",
            cuda: "13.0",
            cuda_available: true,
            gpu_name: "NVIDIA GeForce RTX 3070",
            capability: [8, 6],
            driver: "621.24",
            system: "Windows",
            machine: "AMD64",
        },
        triton: {
            supported: true,
            installed: "3.8.0.post29",
            latest: "3.8.0.post29",
            status: "Up to date",
            message: "Compatible Triton is installed.",
        },
        sageattention: {
            supported: false,
            installed: "2.2.0+cu130torch210",
            status: "Prerequisite missing",
            message: "A PyTorch-matched Triton build is required.",
            triton_note: "Triton is not installed.",
        },
    };
}

async function flushPromises() {
    await Promise.resolve();
    await Promise.resolve();
    await new Promise((resolve) => setTimeout(resolve, 0));
}

function setup() {
    const { extension, document } = loadExtension(makeReport());
    class Node {
        onRemoved() {}
    }
    extension.beforeRegisterNodeDef(Node, { name: "PhantomGodEnvironmentManager" });
    const node = new Node();
    Object.assign(node, {
        type: "PhantomGodEnvironmentManager",
        comfyClass: "PhantomGodEnvironmentManager",
        size: [430, 440],
        widgets: [],
        addDOMWidget(name, type, element, options) {
            const widget = { name, type, element, options };
            this.widgets.push(widget);
            return widget;
        },
        setDirtyCanvas() {},
    });
    extension.nodeCreated(node);
    return { extension, document, node };
}

test("registers the Environment Manager frontend extension", () => {
    const { extension } = loadExtension(makeReport());
    assert.equal(extension.name, "PhantomGod.EnvironmentManager");
});

test("disables SageAttention installation when Triton prerequisite is missing", async () => {
    const { node } = setup();
    await flushPromises();

    const root = node.__phantomGodEnvRoot;
    const triton = root.children[2];
    const sage = root.children[3];

    assert.equal(triton.children[0].children[1].textContent, "Up to date");
    assert.equal(triton.children[3].children[1].disabled, false);
    assert.equal(sage.children[0].children[1].textContent, "Prerequisite missing");
    const sageActions = sage.children.find((child) => child.className === "pg-env-actions");
    assert.ok(sageActions);
    assert.equal(sageActions.children[1].disabled, true);
    assert.match(sage.children[1].textContent, /Triton build is required/);
});

test("Environment Manager recomputes layout from the rendered content", async () => {
    const { node } = setup();
    await flushPromises();

    for (const child of node.__phantomGodEnvRoot.children) child.offsetHeight = 120;
    const layout = node.__phantomGodEnvWidget.computeLayoutSize();
    assert.ok(layout.minHeight > 600);
    assert.equal(layout.minWidth, 390);
    assert.equal(node.__phantomGodEnvWidget.options.getMinHeight(), layout.minHeight);
});

test("removing the node releases its DOM root and stops client polling", async () => {
    const { node } = setup();
    await flushPromises();
    const root = node.__phantomGodEnvRoot;

    node.onRemoved();
    assert.equal(node.__phantomGodEnvRemoved, true);
    assert.equal(root.removed, true);
    assert.equal(node.__phantomGodEnvRoot, null);
});
