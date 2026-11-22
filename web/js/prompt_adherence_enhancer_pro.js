import { app } from "../../scripts/app.js";

const NODE_NAME = "PromptAdherenceEnhancerPro";
const MODEL_WIDGET = "Auto-detected model";
const DETAILS_WIDGET = "Detection / adapter details";

function setReadOnly(widget) {
    if (!widget) return;
    // UI-only widgets must be excluded from both workflow widget values and
    // API prompt inputs. The detected result itself is persisted in node.properties.
    widget.serialize = false;
    widget.options = { ...(widget.options ?? {}), serialize: false };
    widget.disabled = true;
    if (widget.inputEl) {
        widget.inputEl.readOnly = true;
        widget.inputEl.setAttribute("aria-readonly", "true");
        widget.inputEl.style.cursor = "default";
        widget.inputEl.style.opacity = "0.9";
    }
}

function updateWidget(node, name, value) {
    const widget = node.widgets?.find((candidate) => candidate.name === name);
    if (!widget) return;
    widget.value = String(value ?? "");
    if (widget.inputEl) {
        widget.inputEl.value = widget.value;
        widget.inputEl.title = widget.value;
    }
}

function restoreSavedDetection(node) {
    const properties = node.properties ?? {};
    updateWidget(node, MODEL_WIDGET, properties.paa_detected_model ?? "Not detected yet — queue the workflow");
    updateWidget(node, DETAILS_WIDGET, properties.paa_detection_details ?? "Detection runs automatically from the connected MODEL architecture.");
}

app.registerExtension({
    name: "Comfy.PromptAdherenceEnhancerPro.ModelDetection",

    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== NODE_NAME) return;

        const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            originalOnNodeCreated?.apply(this, arguments);

            this.properties = this.properties ?? {};
            if (!this.widgets?.some((widget) => widget.name === MODEL_WIDGET)) {
                const modelWidget = this.addWidget(
                    "text",
                    "Auto-detected model",
                    "Not detected yet — queue the workflow",
                    () => {},
                    { serialize: false }
                );
                setReadOnly(modelWidget);
            }

            if (!this.widgets?.some((widget) => widget.name === DETAILS_WIDGET)) {
                const detailsWidget = this.addWidget(
                    "text",
                    "Detection / adapter details",
                    "Detection runs automatically from the connected MODEL architecture.",
                    () => {},
                    { serialize: false }
                );
                setReadOnly(detailsWidget);
            }

            restoreSavedDetection(this);
            const size = this.computeSize?.();
            if (size && this.setSize) {
                this.setSize([Math.max(size[0], 460), size[1]]);
            }
        };

        const originalOnExecuted = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            originalOnExecuted?.apply(this, arguments);

            const detectedModel = message?.detected_model?.[0] ?? "Detection result unavailable";
            const details = message?.detection_details?.[0] ?? "No model details were returned by the backend.";

            this.properties = this.properties ?? {};
            this.properties.paa_detected_model = String(detectedModel);
            this.properties.paa_detection_details = String(details);

            updateWidget(this, MODEL_WIDGET, detectedModel);
            updateWidget(this, DETAILS_WIDGET, details);
            this.setDirtyCanvas?.(true, true);
            this.graph?.setDirtyCanvas?.(true, true);
        };

        const originalOnConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            originalOnConfigure?.apply(this, arguments);
            restoreSavedDetection(this);
        };
    },
});
