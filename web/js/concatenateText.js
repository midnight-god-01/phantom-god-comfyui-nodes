import { app } from "../../scripts/app.js";
import { ComfyWidgets } from "../../scripts/widgets.js";

const EXTENSION_NAME = "PhantomGod.ConcatenateText";
const NODE_TYPE = "PhantomGodConcatenateText";
const TEXT_INPUT_NAME = /^text_(\d+)$/;
const CONTROL_WIDGET_NAME = "text_controls";
const ADD_BUTTON_NAME = "Add Text";

function isTextInputName(name) {
    const match = TEXT_INPUT_NAME.exec(name ?? "");
    return Boolean(match && Number(match[1]) >= 1);
}

function getTextInputIndices(inputs = []) {
    return inputs
        .map((input) => TEXT_INPUT_NAME.exec(input?.name ?? ""))
        .filter((match) => match && Number(match[1]) >= 1)
        .map((match) => Number(match[1]))
        .filter((index, position, indices) => indices.indexOf(index) === position)
        .sort((a, b) => a - b);
}

function getRemoveState(node) {
    const raw = node.properties?.phantomGodTextRemoveState;
    if (typeof raw === "string") {
        try { return JSON.parse(raw) || {}; } catch { return {}; }
    }
    return raw && typeof raw === "object" ? raw : {};
}

function setRemoveState(node, index, removed) {
    node.properties ??= {};
    const state = getRemoveState(node);
    if (removed) state[index] = true;
    else delete state[index];
    node.properties.phantomGodTextRemoveState = state;
    node.graph?.change?.();
    node.graph?.incrementVersion?.();
}

function isRemoved(node, index) {
    return Boolean(getRemoveState(node)[index]);
}

function moveWidgetBeforeControls(node, widget) {
    const widgets = node.widgets ?? [];
    const controls = node.__phantomGodTextControls;
    if (!controls || widget === controls) return;

    const widgetIndex = widgets.indexOf(widget);
    const controlsIndex = widgets.indexOf(controls);
    if (widgetIndex !== -1 && controlsIndex !== -1 && widgetIndex > controlsIndex) {
        widgets.splice(widgetIndex, 1);
        widgets.splice(controlsIndex, 0, widget);
    }
}

function ensureTextWidget(node, index, defaultValue = "") {
    const name = "text_" + index;
    let widget = node.widgets?.find((candidate) => candidate.name === name);

    if (!widget) {
        const result = ComfyWidgets.STRING(
            node,
            name,
            ["STRING", {
                default: defaultValue,
                multiline: true,
                placeholder: "Text " + index,
            }],
            app,
        );
        widget = result?.widget ?? node.widgets?.find((candidate) => candidate.name === name);
    }

    if (!widget) throw new Error("ComfyUI did not create the " + name + " text widget.");
    widget.options ??= {};
    widget.options.multiline = true;
    widget.options.placeholder = "Text " + index;
    widget.label = "Text " + index;
    moveWidgetBeforeControls(node, widget);
    return widget;
}

function ensureTextSocket(node, index) {
    const name = "text_" + index;
    let input = node.inputs?.find((slot) => slot.name === name);

    if (!input) {
        node.addInput(name, "STRING", {
            label: "Text " + index,
            widget: { name },
        });
        input = node.inputs?.find((slot) => slot.name === name);
    }

    if (input) {
        input.type = "STRING";
        input.label = "Text " + index;
        input.widget = { ...(input.widget ?? {}), name };
    }
    return input;
}

function ensureTextField(node, index, defaultValue = "") {
    const widget = ensureTextWidget(node, index, defaultValue);
    ensureTextSocket(node, index);
    return widget;
}

function removeWidget(node, name) {
    const widgets = node.widgets ?? [];
    const index = widgets.findIndex((widget) => widget.name === name);
    if (index < 0) return;
    const [widget] = widgets.splice(index, 1);
    widget.onRemove?.();
    widget.element?.remove?.();
}

function createButton(text, className, title, callback) {
    const item = document.createElement("button");
    item.type = "button";
    item.className = className;
    item.textContent = text;
    item.title = title;
    item.addEventListener("click", (event) => {
        event?.preventDefault?.();
        event?.stopPropagation?.();
        callback();
    });
    return item;
}

function updateControlLayout(node) {
    const dom = node.__phantomGodTextControls;
    if (!dom) return;
    const count = getTextInputIndices(node.inputs).length;
    const height = 55 + count * 37;
    dom.computeLayoutSize = () => ({
        minHeight: height,
        maxHeight: height,
        minWidth: 160,
    });
    dom.options.getMinHeight = () => height;
    dom.options.getMaxHeight = () => height;
}

function renderTextControls(node) {
    const root = node.__phantomGodTextControls?.element || node.__phantomGodTextControlRoot;
    if (!root) return;

    root.replaceChildren?.();
    root.innerHTML = "";
    root.className = "pg-text-controls";

    const header = document.createElement("div");
    header.className = "pg-text-header";
    header.appendChild(element("div", "pg-text-eyebrow", "TEXT INPUTS"));
    header.appendChild(element("div", "pg-text-count", getTextInputIndices(node.inputs).length + " FIELDS"));
    root.appendChild(header);

    const fieldList = document.createElement("div");
    fieldList.className = "pg-text-field-list";
    for (const index of getTextInputIndices(node.inputs)) {
        const row = document.createElement("div");
        row.className = "pg-text-field-row";
        row.dataset.textIndex = String(index);
        const label = element("span", "pg-text-field-label", "TEXT " + index);
        const state = createButton(
            isRemoved(node, index) ? "OFF" : "ON",
            "pg-text-field-toggle" + (isRemoved(node, index) ? "" : " pg-on"),
            isRemoved(node, index) ? "Restore Text " + index : "Hide Text " + index,
            () => {
                const next = !isRemoved(node, index);
                setRemoveState(node, index, next);
                const input = node.inputs?.find((slot) => slot.name === "text_" + index);
                if (input) input.pgHidden = next;
                const widget = node.widgets?.find((candidate) => candidate.name === "text_" + index);
                if (widget) widget.disabled = next;
                renderTextControls(node);
                refreshNode(node);
            },
        );
        state.dataset.textIndex = String(index);
        state.setAttribute("aria-pressed", isRemoved(node, index) ? "false" : "true");
        const remove = createButton(
            "×",
            "pg-text-field-delete",
            "Remove Text " + index + " completely",
            () => removeTextInput(node, index),
        );
        remove.dataset.textIndex = String(index);
        row.append(label, state, remove);
        fieldList.appendChild(row);
    }
    root.appendChild(fieldList);

    const footer = document.createElement("div");
    footer.className = "pg-text-footer";
    footer.appendChild(createButton(
        "＋  Add text field",
        "pg-text-add",
        "Add another text field",
        () => addTextInput(node),
    ));
    root.appendChild(footer);
}

function element(tag, className, text) {
    const item = document.createElement(tag);
    if (className) item.className = className;
    if (text !== undefined) item.textContent = String(text);
    return item;
}

function refreshNode(node) {
    updateControlLayout(node);
    node.setDirtyCanvas?.(true, true);
    app.graph?.setDirtyCanvas?.(true, true);
}

function applyAdaptiveCanvasOnly(widget) {
    if (!widget?.options) return;
    try {
        Object.defineProperty(widget.options, "canvasOnly", {
            configurable: true,
            enumerable: true,
            get() { return !window.LiteGraph?.vueNodesMode; },
        });
    } catch {
        // Older LiteGraph versions can expose immutable options.
    }
}

function addTextInput(node) {
    const nextIndex = Math.max(0, ...getTextInputIndices(node.inputs)) + 1;
    ensureTextField(node, nextIndex, "");
    renderTextControls(node);
    refreshNode(node);
}

function removeTextInput(node, index) {
    const name = "text_" + index;
    const inputIndex = node.inputs?.findIndex((input) => input.name === name) ?? -1;
    if (inputIndex >= 0 && typeof node.removeInput === "function") {
        node.removeInput(inputIndex);
    } else if (inputIndex >= 0) {
        node.inputs.splice(inputIndex, 1);
    }
    removeWidget(node, name);
    const state = getRemoveState(node);
    delete state[index];
    node.properties.phantomGodTextRemoveState = state;
    renderTextControls(node);
    refreshNode(node);
}

function injectStyles() {
    if (document.getElementById("phantom-god-text-controls-style")) return;
    const style = document.createElement("style");
    style.id = "phantom-god-text-controls-style";
    style.textContent = [
        ".pg-text-controls{display:flex;flex-direction:column;gap:8px;width:100%;min-width:0;box-sizing:border-box;padding:3px 1px 1px;color:var(--input-text,#eee);font:12px Inter,system-ui,sans-serif;}",
        ".pg-text-controls *{box-sizing:border-box;}",
        ".pg-text-header{display:flex;align-items:center;justify-content:space-between;gap:8px;min-width:0;}",
        ".pg-text-eyebrow{color:var(--descrip-text,#888);font-size:9px;font-weight:700;letter-spacing:.12em;}",
        ".pg-text-count{color:var(--descrip-text,#777);font:10px ui-monospace,monospace;}",
        ".pg-text-field-list{display:flex;flex-direction:column;gap:5px;width:100%;min-width:0;}",
        ".pg-text-field-row{display:grid;grid-template-columns:minmax(0,1fr) 48px 28px;align-items:center;gap:6px;min-width:0;padding:5px 6px;border:1px solid var(--border-color,rgba(255,255,255,.12));border-radius:6px;background:rgba(255,255,255,.025);}",
        ".pg-text-field-label{min-width:0;color:var(--descrip-text,#aaa);font-size:10px;font-weight:600;letter-spacing:.04em;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}",
        ".pg-text-controls button{font:inherit;white-space:nowrap;cursor:pointer;transition:background .14s,border-color .14s,color .14s;}",
        ".pg-text-field-toggle{height:26px;padding:3px 6px;border:1px solid rgba(255,255,255,.18);border-radius:5px;background:rgba(255,255,255,.04);color:var(--descrip-text,#aaa);font-size:10px;font-weight:700;}",
        ".pg-text-field-toggle.pg-on{border-color:rgba(93,177,124,.6);background:rgba(53,135,83,.18);color:#a8e2b9;}",
        ".pg-text-field-delete{height:26px;padding:2px 5px;border:1px solid rgba(220,90,90,.32);border-radius:5px;background:rgba(150,45,45,.1);color:#d9958d;font-size:15px;}",
        ".pg-text-field-delete:hover{border-color:#d66;background:rgba(170,50,50,.25);color:#fff;}",
        ".pg-text-add{width:100%;min-height:34px;padding:7px 12px;border:1px solid var(--border-color,rgba(255,255,255,.16));border-radius:6px;background:var(--comfy-input-bg,#282828);color:var(--input-text,#eee);font-weight:600;text-align:center;}",
        ".pg-text-add:hover{border-color:var(--p-primary,#8b9b9b);background:var(--comfy-menu-bg,#383838);}",
    ].join("");
    document.head.appendChild(style);
}

function installTextControls(node) {
    if (node.__phantomGodTextControls || typeof node.addDOMWidget !== "function") return;
    injectStyles();

    const root = document.createElement("div");
    root.className = "pg-text-controls";
    node.__phantomGodTextControlRoot = root;
    const widget = node.addDOMWidget(CONTROL_WIDGET_NAME, "phantom_god_text_controls", root, {
        getValue: () => "",
        setValue: () => {},
        getMinHeight: () => 44,
        getMaxHeight: () => 2000,
        margin: 4,
        serialize: false,
    });
    widget.computeLayoutSize = () => ({ minHeight: 44, minWidth: 160 });
    node.__phantomGodTextControls = widget;
    applyAdaptiveCanvasOnly(widget);
    renderTextControls(node);
    updateControlLayout(node);
}

function reconcileTextFields(node, workflowNode) {
    const savedInputs = workflowNode?.inputs;
    if (!Array.isArray(savedInputs)) return;
    const savedNames = new Set(savedInputs.map((input) => input?.name).filter(isTextInputName));

    for (const widget of [...(node.widgets ?? [])]) {
        if (isTextInputName(widget?.name) && !savedNames.has(widget.name)) {
            removeWidget(node, widget.name);
        }
    }

    const indices = getTextInputIndices(savedInputs);
    const namedValues = workflowNode?.widgets_values_named ?? {};
    const positionalValues = workflowNode?.widgets_values ?? [];
    indices.forEach((index, position) => {
        const name = "text_" + index;
        const hasNamedValue = Object.prototype.hasOwnProperty.call(namedValues, name);
        const savedValue = hasNamedValue ? namedValues[name] : (positionalValues[position + 1] ?? "");
        const widget = ensureTextField(node, index, savedValue);
        if (hasNamedValue || positionalValues.length > position + 1) widget.value = savedValue;
    });
}

function applyHiddenStates(node) {
    for (const index of getTextInputIndices(node.inputs)) {
        const hidden = isRemoved(node, index);
        const input = node.inputs?.find((slot) => slot.name === "text_" + index);
        if (input) input.pgHidden = hidden;
        const widget = node.widgets?.find((candidate) => candidate.name === "text_" + index);
        if (widget) widget.disabled = hidden;
    }
}

function patchNodeType(nodeType) {
    const prototype = nodeType?.prototype;
    if (!prototype || prototype.__phantomGodConcatenateTextPatched) return;

    const originalOnNodeCreated = prototype.onNodeCreated;
    prototype.onNodeCreated = function (...args) {
        const result = originalOnNodeCreated?.apply(this, args);
        this.properties ??= {};
        installTextControls(this);
        return result;
    };

    const originalOnConfigure = prototype.onConfigure;
    prototype.onConfigure = function (workflowNode, ...args) {
        const result = originalOnConfigure?.call(this, workflowNode, ...args);
        this.properties ??= {};
        reconcileTextFields(this, workflowNode);
        applyHiddenStates(this);
        renderTextControls(this);
        refreshNode(this);
        return result;
    };

    const originalOnResize = prototype.onResize;
    prototype.onResize = function (...args) {
        const result = originalOnResize?.apply(this, args);
        refreshNode(this);
        return result;
    };

    const originalRemoved = prototype.onRemoved;
    prototype.onRemoved = function (...args) {
        this.__phantomGodTextControlRoot?.remove?.();
        return originalRemoved?.apply(this, args);
    };

    prototype.__phantomGodConcatenateTextPatched = true;
}

app.registerExtension({
    name: EXTENSION_NAME,
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData?.name === NODE_TYPE) patchNodeType(nodeType);
    },
    nodeCreated(node) {
        if (node?.type !== NODE_TYPE && node?.comfyClass !== NODE_TYPE) return;
        node.properties ??= {};
        installTextControls(node);
        applyHiddenStates(node);
        renderTextControls(node);
    },
});

console.info("[Phantom God] Concatenate Text feature loaded.");
