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

function loadExtension(report, vueNodesMode = true) {
    const script = source
        .replace('import { app } from "../../scripts/app.js";\n', "")
        .replace('import { api } from "../../scripts/api.js";\n', "");
    assert.notEqual(script, source);

    const extensions = [];
    const document = makeDocument();
    const app = { graph: { setDirtyCanvas() {} }, registerExtension(ext) { extensions.push(ext); } };
    const requests = { check: 0 };
    const api = {
        async fetchApi(route) {
            assert.equal(route, "/phantom_god/environment/check");
            requests.check += 1;
            return { ok: true, async json() { return report; } };
        },
    };
    runInNewContext(script, {
        app, api, document,
        window: { LiteGraph: { vueNodesMode } },
        console: { info() {}, warn() {}, error() {} },
    });
    return { extension: extensions[0], document, requests };
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

function setup({ vueNodesMode = true, requiredHeight = null, size = [430, 440] } = {}) {
    const { extension, document, requests } = loadExtension(makeReport(), vueNodesMode);
    class Node {
        onNodeCreated() {}
        onAdded() {}
        onRemoved() {}
    }
    extension.beforeRegisterNodeDef(Node, { name: "PhantomGodEnvironmentManager" });
    const node = new Node();
    Object.assign(node, {
        type: "PhantomGodEnvironmentManager",
        comfyClass: "PhantomGodEnvironmentManager",
        size: [...size],
        widgets: [],
        sizeCalls: 0,
        computeSize() {
            const content = this.__phantomGodEnvWidget?.computeLayoutSize?.().minHeight ?? 430;
            return [430, requiredHeight ?? (content + 20)];
        },
        setSize(next) {
            this.size = [...next];
            this.sizeCalls += 1;
        },
        addDOMWidget(name, type, element, options) {
            const widget = { name, type, element, options };
            this.widgets.push(widget);
            return widget;
        },
        setDirtyCanvas() {},
    });
    extension.nodeCreated(node);
    return { extension, document, node, requests };
}

test("registers the Environment Manager frontend extension", () => {
    const { extension } = loadExtension(makeReport());
    assert.equal(extension.name, "PhantomGod.EnvironmentManager");
});


test("does not scan the environment when the node is created", async () => {
    const { node, requests } = setup();
    await flushPromises();
    assert.equal(requests.check, 0);
    assert.equal(node.__phantomGodEnvReport, undefined);
    assert.match(node.__phantomGodEnvRoot.children[1].children[1].textContent, /Select Check Environment/);
});

test("shows a visible error widget when addDOMWidget is unavailable", () => {
    const { extension } = loadExtension(makeReport());
    class Node {
        onNodeCreated() {}
        onAdded() {}
        onRemoved() {}
    }
    extension.beforeRegisterNodeDef(Node, { name: "PhantomGodEnvironmentManager" });
    const node = new Node();
    node.type = "PhantomGodEnvironmentManager";
    node.widgets = [];
    node.addWidget = (...args) => {
        node.fallbackArgs = args;
        return { name: args[1] };
    };

    node.onAdded();

    assert.ok(node.__phantomGodEnvFallbackWidget);
    assert.equal(node.fallbackArgs[1], "Environment Manager UI error");
    assert.match(node.fallbackArgs[2], /addDOMWidget API/);
});

test("Environment Manager DOM widget targets the active frontend render surface", () => {
    const vueSetup = setup({ vueNodesMode: true });
    const classicSetup = setup({ vueNodesMode: false });

    assert.equal(vueSetup.node.__phantomGodEnvWidget.options.canvasOnly, false);
    assert.equal(classicSetup.node.__phantomGodEnvWidget.options.canvasOnly, true);
});

test("initializes Environment Manager from the node-added fallback", () => {
    const { extension } = loadExtension(makeReport());
    class Node {
        onNodeCreated() {}
        onAdded() {}
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

    node.onAdded();

    assert.ok(node.__phantomGodEnvRoot);
    assert.ok(node.__phantomGodEnvWidget);
    assert.equal(node.__phantomGodEnvRoot.children.length, 5);
});

test("runs an environment scan only after an explicit Check All action", async () => {
    const { node, requests } = setup();
    node.__phantomGodEnvRoot.children[0].children[1].click();
    await flushPromises();
    assert.equal(requests.check, 1);
    assert.ok(node.__phantomGodEnvReport);
});

test("disables SageAttention installation when Triton prerequisite is missing", async () => {
    const { node } = setup();
    node.__phantomGodEnvRoot.children[0].children[1].click();
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


test("Classic LiteGraph expands the Environment Manager node to its rendered widget size", () => {
    const { node } = setup({
        vueNodesMode: false,
        requiredHeight: 760,
        size: [350, 200],
    });

    assert.deepEqual(Array.from(node.size), [430, 760]);
    assert.equal(node.sizeCalls, 1);
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
