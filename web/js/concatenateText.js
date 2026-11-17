import { app } from "../../scripts/app.js";
import { ComfyWidgets } from "../../scripts/widgets.js";

const EXTENSION_NAME = "PhantomGod.ConcatenateText";
const NODE_TYPE = "PhantomGodConcatenateText";
const TEXT_INPUT_NAME = /^text_(\d+)$/;
const FIRST_DYNAMIC_INPUT = 3;
const STATIC_WIDGET_COUNT = 3; // delimiter, text_1, text_2
const ADD_BUTTON_NAME = "Add Text";

function isConcatenateNode(node) {
    return node?.type === NODE_TYPE
        || node?.comfyClass === NODE_TYPE
        || node?.constructor?.type === NODE_TYPE;
}

function getDynamicInputIndices(inputs = []) {
    return inputs
        .map((input) => TEXT_INPUT_NAME.exec(input?.name ?? ""))
        .filter((match) => match && Number(match[1]) >= FIRST_DYNAMIC_INPUT)
        .map((match) => Number(match[1]))
        .filter((index, position, indices) => indices.indexOf(index) === position)
        .sort((a, b) => a - b);
}

function moveWidgetBeforeAddButton(node, widget) {
    const widgets = node.widgets ?? [];
    const button = node.__phantomGodAddTextButton;
    if (!button || widget === button) return;

    const widgetIndex = widgets.indexOf(widget);
    const buttonIndex = widgets.indexOf(button);
    if (widgetIndex !== -1 && buttonIndex !== -1 && widgetIndex > buttonIndex) {
        widgets.splice(widgetIndex, 1);
        widgets.splice(buttonIndex, 0, widget);
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
                placeholder: "Enter text " + index + "...",
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
    widget.options.placeholder ??= "Enter text " + index + "...";
    moveWidgetBeforeAddButton(node, widget);
    return widget;
}

function ensureTextSocket(node, index) {
    const name = "text_" + index;
    let input = node.inputs?.find((slot) => slot.name === name);

    if (!input) {
        node.addInput(name, "STRING", { widget: { name } });
        input = node.inputs?.find((slot) => slot.name === name);
    }

    if (input) {
        input.type = "STRING";
        input.widget = { ...(input.widget ?? {}), name };
    }
    return input;
}

function ensureTextField(node, index, defaultValue = "") {
    const widget = ensureTextWidget(node, index, defaultValue);
    ensureTextSocket(node, index);
    return widget;
}

function refreshNode(node) {
    if (typeof node.computeSize === "function" && typeof node.setSize === "function") {
        node.setSize(node.computeSize());
    }
    node.setDirtyCanvas?.(true, true);
    app.graph?.setDirtyCanvas?.(true, true);
}

function addTextInput(node) {
    const highestIndex = Math.max(2, ...getDynamicInputIndices(node.inputs));
    const nextIndex = highestIndex + 1;
    ensureTextField(node, nextIndex, "");
    refreshNode(node);
}

function installAddButton(node) {
    if (node.__phantomGodAddTextButton || typeof node.addWidget !== "function") return;

    const button = node.addWidget(
        "button",
        ADD_BUTTON_NAME,
        ADD_BUTTON_NAME,
        () => addTextInput(node),
        {},
    );
    // The button is a UI control, not workflow data. Excluding it keeps saved
    // widget values aligned with delimiter, text_1, text_2, text_3, ... .
    button.serialize = false;
    node.__phantomGodAddTextButton = button;
}

function restoreDynamicFields(node, workflowNode) {
    const indices = getDynamicInputIndices(workflowNode?.inputs ?? node.inputs);
    const savedValues = workflowNode?.widgets_values ?? [];

    indices.forEach((index, position) => {
        const savedValue = savedValues[STATIC_WIDGET_COUNT + position] ?? "";
        const widget = ensureTextField(node, index, savedValue);
        widget.value = savedValue;
    });

    refreshNode(node);
}

function patchNodeType(nodeType) {
    const prototype = nodeType?.prototype;
    if (!prototype || prototype.__phantomGodConcatenateTextPatched) return;

    const originalOnNodeCreated = prototype.onNodeCreated;
    prototype.onNodeCreated = function (...args) {
        const result = originalOnNodeCreated?.apply(this, args);
        installAddButton(this);
        return result;
    };

    const originalOnConfigure = prototype.onConfigure;
    prototype.onConfigure = function (workflowNode, ...args) {
        const result = originalOnConfigure?.call(this, workflowNode, ...args);
        // LiteGraph calls onConfigure after restoring its standard widgets and
        // input slots. Recreate our extra widgets from the saved input names,
        // then explicitly restore their values from widgets_values.
        restoreDynamicFields(this, workflowNode);
        return result;
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

    // The nodeCreated hook also covers ComfyUI versions that instantiate a
    // registered node without invoking a custom onNodeCreated override.
    nodeCreated(node) {
        if (isConcatenateNode(node)) {
            installAddButton(node);
        }
    },
});

console.info("[Phantom God] Concatenate Text feature loaded.");
