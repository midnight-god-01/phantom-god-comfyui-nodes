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

    if (!widget) {
        throw new Error("ComfyUI did not create the " + name + " text widget.");
    }

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

function removeTextInput(node, index) {
    const name = "text_" + index;
    const inputIndex = node.inputs?.findIndex((input) => input.name === name) ?? -1;

    // LiteGraph's removeInput also disconnects any link attached to this input.
    if (inputIndex >= 0 && typeof node.removeInput === "function") {
        node.removeInput(inputIndex);
    } else if (inputIndex >= 0) {
        node.inputs.splice(inputIndex, 1);
    }

    removeWidget(node, name);
    renderTextControls(node);
    refreshNode(node);
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

function renderTextControls(node) {
    const root = node.__phantomGodTextControls?.element || node.__phantomGodTextControlRoot;
    if (!root) return;

    root.innerHTML = "";
    root.className = "pg-text-controls";

    const addButton = createButton(
        ADD_BUTTON_NAME,
        "pg-text-add",
        "Add another text field",
        () => addTextInput(node),
    );
    root.appendChild(addButton);

    const removeList = document.createElement("div");
    removeList.className = "pg-text-remove-list";

    for (const index of getTextInputIndices(node.inputs)) {
        const removeButton = createButton(
            "× Text " + index,
            "pg-text-remove",
            "Remove Text " + index,
            () => removeTextInput(node, index),
        );
        removeButton.dataset.textIndex = String(index);
        removeList.appendChild(removeButton);
    }

    root.appendChild(removeList);
}

function refreshNode(node) {
    if (!window.LiteGraph?.vueNodesMode &&
        typeof node.computeSize === "function" &&
        typeof node.setSize === "function") {
        const size = node.computeSize();
        if (size?.[1]) node.setSize([Math.max(node.size?.[0] ?? 0, 320), size[1]]);
    }
    node.setDirtyCanvas?.(true, true);
    app.graph?.setDirtyCanvas?.(true, true);
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
        // Some older LiteGraph versions expose immutable widget options.
    }
}

function addTextInput(node) {
    const highestIndex = Math.max(0, ...getTextInputIndices(node.inputs));
    const nextIndex = highestIndex + 1;
    ensureTextField(node, nextIndex, "");
    renderTextControls(node);
    refreshNode(node);
}

function injectStyles() {
    if (document.getElementById("phantom-god-text-controls-style")) return;
    const style = document.createElement("style");
    style.id = "phantom-god-text-controls-style";
    style.textContent = [
        ".pg-text-controls{display:flex;align-items:center;gap:7px;width:100%;min-width:0;box-sizing:border-box;overflow:hidden;font:12px sans-serif;}",
        ".pg-text-controls button{box-sizing:border-box;white-space:nowrap;cursor:pointer;transition:background .12s,border-color .12s,color .12s;}",
        ".pg-text-add{flex:0 0 auto;padding:6px 12px;border:1px solid var(--input-border,rgba(255,255,255,.18));border-radius:6px;background:var(--comfy-input-bg,#303030);color:var(--input-text,#eee);font-size:12px;}",
        ".pg-text-add:hover{border-color:var(--p-primary,#888);background:var(--comfy-menu-bg,#3a3a3a);}",
        ".pg-text-remove-list{display:flex;align-items:center;gap:5px;min-width:0;overflow-x:auto;scrollbar-width:thin;}",
        ".pg-text-remove{flex:0 0 auto;padding:5px 8px;border:1px solid rgba(220,90,90,.38);border-radius:5px;background:rgba(150,45,45,.12);color:var(--input-text,#ddd);font-size:11px;}",
        ".pg-text-remove:hover{border-color:#d66;background:rgba(170,50,50,.28);color:#fff;}",
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
        getMinHeight: () => 38,
        getMaxHeight: () => 38,
        margin: 4,
        serialize: false,
    });
    widget.computeLayoutSize = () => ({ minHeight: 38, minWidth: 1 });
    node.__phantomGodTextControls = widget;
    applyAdaptiveCanvasOnly(widget);
    renderTextControls(node);
}

function reconcileTextFields(node, workflowNode) {
    const savedInputs = workflowNode?.inputs;
    if (!Array.isArray(savedInputs)) return;

    const savedNames = new Set(savedInputs.map((input) => input?.name).filter(isTextInputName));

    // All text fields are optional, so even the initial two can be removed.
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
        if (hasNamedValue || positionalValues.length > position + 1) {
            widget.value = savedValue;
        }
    });
}

function patchNodeType(nodeType) {
    const prototype = nodeType?.prototype;
    if (!prototype || prototype.__phantomGodConcatenateTextPatched) return;

    const originalOnNodeCreated = prototype.onNodeCreated;
    prototype.onNodeCreated = function (...args) {
        const result = originalOnNodeCreated?.apply(this, args);
        installTextControls(this);
        return result;
    };

    const originalOnConfigure = prototype.onConfigure;
    prototype.onConfigure = function (workflowNode, ...args) {
        const result = originalOnConfigure?.call(this, workflowNode, ...args);
        reconcileTextFields(this, workflowNode);
        renderTextControls(this);
        refreshNode(this);
        return result;
    };

    const originalOnRemoved = prototype.onRemoved;
    prototype.onRemoved = function (...args) {
        this.__phantomGodTextControlRoot?.remove?.();
        return originalOnRemoved?.apply(this, args);
    };

    prototype.__phantomGodConcatenateTextPatched = true;
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
            installTextControls(node);
            for (const index of getTextInputIndices(node.inputs)) {
                const widget = node.widgets?.find((candidate) => candidate.name === "text_" + index);
                const input = node.inputs?.find((candidate) => candidate.name === "text_" + index);
                if (widget) {
                    widget.label = "Text " + index;
                    widget.options ??= {};
                    widget.options.placeholder = "Text " + index;
                }
                if (input) input.label = "Text " + index;
            }
            renderTextControls(node);
        }
    },
});

console.info("[Phantom God] Concatenate Text feature loaded.");
