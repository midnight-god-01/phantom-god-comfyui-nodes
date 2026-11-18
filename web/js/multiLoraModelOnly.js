import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const EXTENSION_NAME = "PhantomGod.MultiLoraModelOnly";
const NODE_TYPE = "PhantomGodMultiLoraModelOnly";
const STATE_PROPERTY = "phantomGodModelLoraState";
const HIDDEN_INPUT = "LoraStackState";
const MIN_STRENGTH = -100;
const MAX_STRENGTH = 100;

let nextId = 1;
let loraNamesPromise = null;
let loraNames = [];
let loraNamesLoaded = false;

function newId() {
    return "pg-lora-" + Date.now().toString(36) + "-" + (nextId++).toString(36);
}

function normalizeRow(row) {
    return {
        id: typeof row?.id === "string" && row.id ? row.id : newId(),
        name: typeof row?.name === "string" ? row.name : "",
        on: row?.on !== false,
        strength: Number.isFinite(Number(row?.strength)) ? Number(row.strength) : 1,
    };
}

function readState(node) {
    const raw = node.properties?.[STATE_PROPERTY];
    let state = raw;
    if (typeof raw === "string") {
        try { state = JSON.parse(raw); } catch { state = null; }
    }
    const rows = Array.isArray(state?.loras) ? state.loras : [];
    return { loras: rows.map(normalizeRow) };
}

function writeState(node, state) {
    node.properties ??= {};
    const safeState = {
        loras: (Array.isArray(state?.loras) ? state.loras : [])
            .map(normalizeRow),
    };
    node.properties[STATE_PROPERTY] = JSON.stringify(safeState);
    node.graph?.change?.();
    node.graph?.incrementVersion?.();
    node.setDirtyCanvas?.(true, true);
    app.graph?.setDirtyCanvas?.(true, true);
    return safeState;
}

function updateRow(node, id, changes) {
    const state = readState(node);
    state.loras = state.loras.map((row) => row.id === id ? { ...row, ...changes } : row);
    writeState(node, state);
    renderNode(node);
}

function addLoraRow(node) {
    const state = readState(node);
    state.loras.push({ id: newId(), name: "", on: true, strength: 1 });
    writeState(node, state);
    renderNode(node);
    fitNode(node);
}

function removeLoraRow(node, id) {
    const state = readState(node);
    state.loras = state.loras.filter((row) => row.id !== id);
    writeState(node, state);
    renderNode(node);
    fitNode(node);
}

async function loadLoraNames(force = false) {
    if (force) {
        loraNamesPromise = null;
        loraNamesLoaded = false;
        loraNames = [];
    }
    if (!loraNamesPromise) {
        loraNamesPromise = api.fetchApi("/models/loras")
            .then(async (response) => {
                if (!response.ok) throw new Error("ComfyUI returned HTTP " + response.status);
                const names = await response.json();
                if (!Array.isArray(names)) throw new Error("ComfyUI returned an invalid LoRA list.");
                loraNames = names
                    .filter((name) => typeof name === "string")
                    .sort((a, b) => a.localeCompare(b));
                loraNamesLoaded = true;
                return loraNames;
            })
            .catch((error) => {
                loraNamesPromise = null;
                loraNamesLoaded = false;
                throw error;
            });
    }
    return loraNamesPromise;
}

function createButton(text, className, title, callback) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = className;
    button.textContent = text;
    button.title = title;
    button.addEventListener("click", (event) => {
        event?.preventDefault?.();
        event?.stopPropagation?.();
        callback();
    });
    return button;
}

function injectStyles() {
    if (document.getElementById("phantom-god-multi-lora-style")) return;
    const style = document.createElement("style");
    style.id = "phantom-god-multi-lora-style";
    style.textContent = [
        ".pg-lora-root{display:flex;flex-direction:column;gap:9px;width:100%;min-width:0;box-sizing:border-box;padding:3px 1px 1px;color:var(--input-text,#eee);font:12px Inter,system-ui,sans-serif;}",
        ".pg-lora-root *{box-sizing:border-box;}",
        ".pg-lora-toolbar{display:grid;grid-template-columns:minmax(0,1fr) 34px auto;align-items:center;gap:7px;min-width:0;}",
        ".pg-lora-root button,.pg-lora-root select,.pg-lora-root input{font:inherit;}",
        ".pg-lora-root button{cursor:pointer;border-radius:5px;transition:background .14s,border-color .14s,color .14s;}",
        ".pg-lora-add{min-width:0;min-height:32px;padding:7px 10px;border:1px solid var(--border-color,rgba(255,255,255,.16));background:var(--comfy-input-bg,#282828);color:var(--input-text,#eee);font-weight:600;}",
        ".pg-lora-add:hover,.pg-lora-refresh:hover{border-color:var(--p-primary,#8b9b9b);background:var(--comfy-menu-bg,#383838);}",
        ".pg-lora-refresh{width:34px;height:32px;border:1px solid var(--border-color,rgba(255,255,255,.16));background:transparent;color:var(--input-text,#ccc);font-size:15px;}",
        ".pg-lora-count{color:var(--descrip-text,#888);font:10px ui-monospace,monospace;white-space:nowrap;}",
        ".pg-lora-rows{display:flex;flex-direction:column;gap:6px;width:100%;min-width:0;}",
        ".pg-lora-row{display:grid;grid-template-columns:minmax(0,1fr) minmax(54px,72px) 44px 28px;align-items:center;gap:5px;width:100%;min-width:0;padding:5px 6px;border:1px solid var(--border-color,rgba(255,255,255,.12));border-radius:6px;background:rgba(255,255,255,.025);}",
        ".pg-lora-row.pg-off{opacity:.48;}",
        ".pg-lora-select,.pg-lora-strength{display:block;width:100%;min-width:0;height:30px;padding:4px 6px;border:1px solid var(--border-color,rgba(255,255,255,.15));border-radius:4px;background:var(--comfy-input-bg,#242424);color:var(--input-text,#eee);}",
        ".pg-lora-select:focus,.pg-lora-strength:focus{outline:1px solid var(--p-primary,#9aa);outline-offset:0;}",
        ".pg-lora-select.pg-missing{color:#e58b80;border-color:rgba(220,95,80,.6);}",
        ".pg-lora-toggle{height:28px;padding:3px 5px;border:1px solid rgba(255,255,255,.18);background:rgba(255,255,255,.04);color:var(--input-text,#ddd);font-size:10px;font-weight:700;letter-spacing:.04em;}",
        ".pg-lora-toggle.pg-on{border-color:rgba(93,177,124,.6);background:rgba(53,135,83,.2);color:#a8e2b9;}",
        ".pg-lora-delete{height:28px;padding:2px 5px;border:1px solid rgba(220,90,90,.32);background:rgba(150,45,45,.1);color:#d9958d;font-size:15px;line-height:1;}",
        ".pg-lora-delete:hover{border-color:#d66;background:rgba(170,50,50,.25);color:#fff;}",
        ".pg-lora-empty,.pg-lora-error{padding:10px;border:1px dashed var(--border-color,rgba(255,255,255,.18));border-radius:5px;color:var(--descrip-text,#999);font-size:11px;line-height:1.5;}",
        ".pg-lora-error{border-color:rgba(220,90,90,.4);color:#e59b91;}",
    ].join("");
    document.head.appendChild(style);
}

function renderNode(node) {
    const root = node.__phantomGodLoraRoot;
    if (!root) return;
    root.innerHTML = "";
    root.className = "pg-lora-root";

    const state = readState(node);
    const toolbar = document.createElement("div");
    toolbar.className = "pg-lora-toolbar";

    const add = createButton(
        "＋ Add LoRA",
        "pg-lora-add",
        "Add another LoRA row",
        () => addLoraRow(node),
    );
    toolbar.appendChild(add);

    const refresh = createButton(
        "↻",
        "pg-lora-refresh",
        "Refresh the LoRA file list",
        async () => {
            try {
                await loadLoraNames(true);
                renderNode(node);
            } catch (error) {
                showError(node, error);
            }
        },
    );
    toolbar.appendChild(refresh);

    const count = document.createElement("span");
    count.className = "pg-lora-count";
    count.textContent = state.loras.length + " ACTIVE ROWS";
    toolbar.appendChild(count);
    root.appendChild(toolbar);

    const rows = document.createElement("div");
    rows.className = "pg-lora-rows";
    root.appendChild(rows);

    if (!state.loras.length) {
        const empty = document.createElement("div");
        empty.className = "pg-lora-empty";
        empty.textContent = "No LoRAs added. Click Add LoRA to create your first row.";
        rows.appendChild(empty);
        fitNode(node);
        return;
    }

    if (!loraNamesLoaded) {
        const loading = document.createElement("div");
        loading.className = "pg-lora-empty";
        loading.textContent = "Loading LoRA files…";
        rows.appendChild(loading);
    }

    for (const row of state.loras) {
        const line = document.createElement("div");
        line.className = "pg-lora-row" + (row.on ? "" : " pg-off");
        line.dataset.rowId = row.id;

        const select = document.createElement("select");
        select.className = "pg-lora-select";
        select.title = "Choose a LoRA file";
        const placeholder = document.createElement("option");
        placeholder.value = "";
        placeholder.textContent = "(select LoRA)";
        select.appendChild(placeholder);

        if (row.name && !loraNames.includes(row.name)) {
            const missing = document.createElement("option");
            missing.value = row.name;
            missing.textContent = "Missing: " + row.name;
            select.appendChild(missing);
            select.className += " pg-missing";
        }

        for (const name of loraNames) {
            const option = document.createElement("option");
            option.value = name;
            option.textContent = name;
            select.appendChild(option);
        }
        select.value = row.name || "";
        select.addEventListener("change", () => {
            updateRow(node, row.id, { name: select.value });
        });
        line.appendChild(select);

        const strength = document.createElement("input");
        strength.type = "number";
        strength.className = "pg-lora-strength";
        strength.min = String(MIN_STRENGTH);
        strength.max = String(MAX_STRENGTH);
        strength.step = "0.01";
        strength.value = String(row.strength);
        strength.title = "Model strength";
        strength.addEventListener("change", () => {
            let value = Number(strength.value);
            if (!Number.isFinite(value)) value = 1;
            value = Math.min(MAX_STRENGTH, Math.max(MIN_STRENGTH, value));
            updateRow(node, row.id, { strength: value });
        });
        line.appendChild(strength);

        const toggle = createButton(
            row.on ? "ON" : "OFF",
            "pg-lora-toggle" + (row.on ? " pg-on" : ""),
            row.on ? "LoRA enabled — click to disable" : "LoRA disabled — click to enable",
            () => updateRow(node, row.id, { on: !row.on }),
        );
        toggle.setAttribute("aria-pressed", row.on ? "true" : "false");
        line.appendChild(toggle);

        const remove = createButton(
            "×",
            "pg-lora-delete",
            "Remove this LoRA row",
            () => removeLoraRow(node, row.id),
        );
        remove.dataset.rowId = row.id;
        line.appendChild(remove);
        rows.appendChild(line);
    }
    fitNode(node);
}

function showError(node, error) {
    const root = node.__phantomGodLoraRoot;
    if (!root) return;
    const message = document.createElement("div");
    message.className = "pg-lora-error";
    message.textContent = error?.message || String(error);
    root.appendChild(message);
    fitNode(node);
}

function applyAdaptiveCanvasOnly(widget) {
    if (!widget?.options) return;
    try {
        Object.defineProperty(widget.options, "canvasOnly", {
            configurable: true,
            enumerable: true,
            get() {
                return !window.LiteGraph?.vueNodesMode;
            },
        });
    } catch {
        // Safe fallback for older LiteGraph widget implementations.
    }
}

function contentHeight(node) {
    const count = readState(node).loras.length;
    const toolbar = 32;
    const rows = count ? count * 42 + (count - 1) * 6 : 38;
    const fallback = 4 + toolbar + 9 + rows;
    const root = node.__phantomGodLoraRoot;
    if (!root?.isConnected || !root.children?.length) return fallback;

    // Measure the actual rendered DOM so loading indicators and error messages
    // are included, and wrapped controls cannot be clipped by an estimated row.
    const children = Array.from(root.children);
    let height = children.reduce(
        (sum, child) => sum + (Number(child.offsetHeight) || 0),
        0,
    );
    const style = globalThis.getComputedStyle?.(root);
    const gap = Number.parseFloat(style?.rowGap || style?.gap) || 9;
    height += gap * Math.max(0, children.length - 1);
    height += Number.parseFloat(style?.paddingTop) || 0;
    height += Number.parseFloat(style?.paddingBottom) || 0;
    return height > 0 ? Math.max(fallback, Math.ceil(height)) : fallback;
}

function fitNode(node) {
    const widget = node.__phantomGodLoraWidget;
    if (widget) {
        const height = contentHeight(node);
        widget.computeLayoutSize = () => ({
            minHeight: contentHeight(node),
            maxHeight: contentHeight(node),
            minWidth: 280,
        });
        widget.options ??= {};
        widget.options.getMinHeight = () => contentHeight(node);
        widget.options.getMaxHeight = () => contentHeight(node);
    }

    // Classic LiteGraph owns the serialized node size. Keep the user's width,
    // but let height follow the full DOM content so rows are never clipped.
    // Nodes 2.0 owns size in its Vue layout store; its DOM widget constraints apply.
    if (!window.LiteGraph?.vueNodesMode &&
        typeof node.computeSize === "function" &&
        typeof node.setSize === "function") {
        const current = node.size || [360, 100];
        const needed = node.computeSize();
        if (Array.isArray(needed)) {
            node.setSize([
                Math.max(280, Number(current[0]) || 0, Number(needed[0]) || 0),
                Math.max(Number(needed[1]) || 0, contentHeight(node) + 46),
            ]);
        }
    }
    node.setDirtyCanvas?.(true, true);
    app.graph?.setDirtyCanvas?.(true, true);
}

function hideStateWidget(node) {
    const widget = node.widgets?.find((item) => item.name === HIDDEN_INPUT);
    if (!widget) return null;

    // Keep the serialized value for graphToPrompt, but never display raw JSON.
    // Nodes 2.0 needs canvasOnly in addition to hidden + zero-size.
    widget.hidden = true;
    widget.computeSize = () => [0, -4];
    widget.options ??= {};
    widget.options.hidden = true;
    widget.options.canvasOnly = true;

    const hideElement = () => {
        const element = widget.element || widget.inputEl;
        if (element?.style) element.style.display = "none";
    };
    hideElement();
    globalThis.requestAnimationFrame?.(hideElement);
    return widget;
}

function setupNode(node) {
    hideStateWidget(node);
    if (node.__phantomGodLoraRoot || typeof node.addDOMWidget !== "function") return;
    injectStyles();
    const root = document.createElement("div");
    root.className = "pg-lora-root";
    node.__phantomGodLoraRoot = root;

    const widget = node.addDOMWidget("lora_stack_ui", "phantom_god_model_lora_stack", root, {
        getValue: () => readState(node),
        setValue: () => {},
        getMinHeight: () => contentHeight(node),
        getMaxHeight: () => contentHeight(node),
        margin: 4,
        serialize: false,
    });
    widget.computeLayoutSize = () => ({
        minHeight: contentHeight(node),
        maxHeight: contentHeight(node),
        minWidth: 280,
    });
    applyAdaptiveCanvasOnly(widget);
    node.__phantomGodLoraWidget = widget;

    renderNode(node);
    fitNode(node);
    loadLoraNames().then(() => {
        if (node.__phantomGodLoraRoot) renderNode(node);
    }).catch((error) => showError(node, error));
}

function buildNodeIndex() {
    const index = new Map();
    const visit = (graph, prefix) => {
        if (!graph) return;
        for (const node of (graph._nodes || graph.nodes || [])) {
            if (!node) continue;
            const compositeId = String(prefix) + node.id;
            if (node.type === NODE_TYPE || node.comfyClass === NODE_TYPE) {
                index.set(compositeId, node);
                if (!index.has(String(node.id))) index.set(String(node.id), node);
            }
            const inner = node.subgraph || node.graph || node._graph;
            if (inner && inner !== graph) visit(inner, compositeId + ":");
        }
    };
    visit(app.graph, "");
    return index;
}

function findNode(index, promptId) {
    const key = String(promptId);
    if (index.has(key)) return index.get(key);
    const tail = key.includes(":") ? key.slice(key.lastIndexOf(":") + 1) : "";
    return tail && index.has(tail) ? index.get(tail) : null;
}

function installPromptStateInjection() {
    // ComfyUI has shipped multiple graphToPrompt result shapes. Inject the
    // saved node state into the generated API prompt before it is queued.
    if (app.__phantomGodModelLoraPromptPatched) return;
    const inject = (result) => {
        const output = result?.output ?? result?.prompt;
        if (!output || typeof output !== "object") return result;

        let index = null;
        for (const promptId of Object.keys(output)) {
            const entry = output[promptId];
            if (entry?.class_type !== NODE_TYPE) continue;
            index ??= buildNodeIndex();
            const node = findNode(index, promptId);
            if (!node) {
                console.warn("[Phantom God] Could not match Multi LoRA node", promptId, "to a canvas node; preserving its generated input.");
                continue;
            }
            const state = readState(node);
            const serialized = JSON.stringify({
                loras: state.loras.map((row) => ({
                    name: row.name,
                    on: Boolean(row.on),
                    strength: row.strength,
                })),
            });
            entry.inputs ??= {};
            entry.inputs[HIDDEN_INPUT] = serialized;
        }
        return result;
    };

    const patchMethod = (target, key) => {
        if (typeof target?.[key] !== "function") return false;
        const original = target[key];
        target[key] = async function (...args) {
            const result = await original.apply(this, args);
            return inject(result);
        };
        return true;
    };

    // The current frontend calls app.graphToPrompt(); leave the lower-level
    // graph implementation untouched to avoid altering unrelated prompt paths.
    if (patchMethod(app, "graphToPrompt")) {
        app.__phantomGodModelLoraPromptPatched = true;
    }
}
function patchNodeType(nodeType) {
    const prototype = nodeType?.prototype;
    if (!prototype || prototype.__phantomGodMultiLoraPatched) return;

    const originalOnResize = prototype.onResize;
    prototype.onResize = function (...args) {
        const result = originalOnResize?.apply(this, args);
        fitNode(this);
        return result;
    };

    const originalOnConfigure = prototype.onConfigure;
    prototype.onConfigure = function (...args) {
        const result = originalOnConfigure?.apply(this, args);
        hideStateWidget(this);
        renderNode(this);
        fitNode(this);
        return result;
    };

    // Some supported frontends invoke onNodeCreated rather than the extension
    // nodeCreated hook for dynamically loaded or cloned graph nodes.
    const originalOnNodeCreated = prototype.onNodeCreated;
    prototype.onNodeCreated = function (...args) {
        const result = originalOnNodeCreated?.apply(this, args);
        setupNode(this);
        return result;
    };

    const originalOnRemoved = prototype.onRemoved;
    prototype.onRemoved = function (...args) {
        this.__phantomGodLoraRoot?.remove?.();
        this.__phantomGodLoraRoot = null;
        this.__phantomGodLoraWidget = null;
        return originalOnRemoved?.apply(this, args);
    };

    prototype.__phantomGodMultiLoraPatched = true;
}

app.registerExtension({
    name: EXTENSION_NAME,

    beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData?.name === NODE_TYPE) {
            patchNodeType(nodeType);
        }
    },

    nodeCreated(node) {
        if (node?.type === NODE_TYPE || node?.comfyClass === NODE_TYPE) {
            setupNode(node);
        }
    },
});

installPromptStateInjection();
console.info("[Phantom God] Multi LoRA Loader (Model Only) feature loaded.");
