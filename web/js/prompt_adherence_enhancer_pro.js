import { app } from "../../scripts/app.js";

const NODE_NAME = "PromptAdherenceEnhancerPro";
const MODEL_WIDGET = "Auto-detected model";
const DETAILS_WIDGET = "Detection / adapter details";
const CLASSIC_PANEL_HEIGHT = 78;
const MIN_NODE_WIDTH = 360;
const VUE_NODE_MIN_WIDTH = 460;

const DEFAULT_MODEL = "Not detected yet — queue the workflow";
const DEFAULT_DETAILS = "Detection runs automatically from the connected MODEL architecture.";

function isVueNodesMode() {
    // ComfyUI exposes this setting through its public UI settings facade.
    // Older frontend builds without the setting API fall back to Classic mode.
    return app?.ui?.settings?.getSettingValue?.("Comfy.VueNodes.Enabled") === true;
}

function setReadOnly(widget) {
    if (!widget) return;
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

function ensureVueWidgets(node) {
    if (typeof node.addWidget !== "function") return;

    if (!node.widgets?.some((widget) => widget.name === MODEL_WIDGET)) {
        const widget = node.addWidget(
            "text",
            MODEL_WIDGET,
            node.properties?.paa_detected_model ?? DEFAULT_MODEL,
            () => {},
            { serialize: false }
        );
        setReadOnly(widget);
    }

    if (!node.widgets?.some((widget) => widget.name === DETAILS_WIDGET)) {
        const widget = node.addWidget(
            "text",
            DETAILS_WIDGET,
            node.properties?.paa_detection_details ?? DEFAULT_DETAILS,
            () => {},
            { serialize: false }
        );
        setReadOnly(widget);
    }
}

function removeVueWidgets(node) {
    const displayWidgets = (node.widgets ?? []).filter(
        (widget) => widget.name === MODEL_WIDGET || widget.name === DETAILS_WIDGET
    );
    for (const widget of displayWidgets) {
        if (typeof node.removeWidget === "function") {
            node.removeWidget(widget);
        } else {
            // A compatibility fallback for older LiteGraph forks.
            widget.hidden = true;
        }
    }
}

function applyRendererLayout(node) {
    const vueMode = isVueNodesMode();
    if (vueMode) {
        ensureVueWidgets(node);
    } else {
        removeVueWidgets(node);
    }

    const measured = node.computeSize?.();
    if (Array.isArray(measured) && node.setSize) {
        const width = Math.max(measured[0] ?? 0, vueMode ? VUE_NODE_MIN_WIDTH : MIN_NODE_WIDTH);
        const height = (measured[1] ?? node.size?.[1] ?? 100) + (vueMode ? 0 : CLASSIC_PANEL_HEIGHT);
        node.setSize([width, height]);
    }

    node.setDirtyCanvas?.(true, true);
    node.graph?.setDirtyCanvas?.(true, true);
}

function restoreSavedDetection(node) {
    const properties = node.properties ?? {};
    updateWidget(node, MODEL_WIDGET, properties.paa_detected_model ?? DEFAULT_MODEL);
    updateWidget(node, DETAILS_WIDGET, properties.paa_detection_details ?? DEFAULT_DETAILS);
}

function wrapText(ctx, text, maxWidth, maxLines = 2) {
    const words = String(text ?? "").split(/\s+/).filter(Boolean);
    const lines = [];
    let line = "";
    let consumed = 0;

    for (const word of words) {
        const candidate = line ? line + " " + word : word;
        if (line && ctx.measureText(candidate).width > maxWidth) {
            lines.push(line);
            consumed += line.split(/\s+/).length;
            line = word;
            if (lines.length >= maxLines) break;
        } else {
            line = candidate;
        }
    }

    if (lines.length < maxLines && line) {
        lines.push(line);
        consumed += line.split(/\s+/).length;
    }
    if (consumed < words.length && lines.length > 0) {
        let last = lines[lines.length - 1];
        while (last && ctx.measureText(last + "…").width > maxWidth) {
            last = last.slice(0, -1);
        }
        lines[lines.length - 1] = last + "…";
    }
    return lines.slice(0, maxLines);
}

function drawClassicDetectionPanel(node, ctx) {
    if (isVueNodesMode() || !ctx || typeof ctx.fillText !== "function") return;

    const width = Math.max(120, (node.size?.[0] ?? MIN_NODE_WIDTH) - 16);
    const panelHeight = CLASSIC_PANEL_HEIGHT - 8;
    const x = 8;
    const y = Math.max(4, (node.size?.[1] ?? panelHeight + 8) - CLASSIC_PANEL_HEIGHT + 4);
    const model = node.properties?.paa_detected_model ?? DEFAULT_MODEL;
    const details = node.properties?.paa_detection_details ?? DEFAULT_DETAILS;

    ctx.save?.();
    ctx.fillStyle = "rgba(16, 20, 25, 0.92)";
    ctx.strokeStyle = "rgba(130, 145, 160, 0.55)";
    ctx.lineWidth = 1;
    ctx.fillRect?.(x, y, width, panelHeight);
    ctx.strokeRect?.(x, y, width, panelHeight);

    ctx.font = "bold 10px sans-serif";
    ctx.fillStyle = "#9ba9b8";
    ctx.fillText("AUTO-DETECTED MODEL", x + 8, y + 14, width - 16);

    ctx.font = "bold 13px sans-serif";
    ctx.fillStyle = "#f0f3f6";
    ctx.fillText(String(model), x + 8, y + 32, width - 16);

    ctx.font = "10px sans-serif";
    ctx.fillStyle = "#c4ccd5";
    const lines = wrapText(ctx, details, width - 16, 2);
    lines.forEach((line, index) => {
        ctx.fillText(line, x + 8, y + 48 + index * 12, width - 16);
    });
    ctx.restore?.();
}

function refreshAllNodes() {
    const graphs = [app?.canvas?.graph];
    const visited = new Set();

    for (const graph of graphs) {
        for (const node of graph?._nodes ?? []) {
            if (visited.has(node) || node.type !== NODE_NAME) continue;
            visited.add(node);
            applyRendererLayout(node);
            restoreSavedDetection(node);
        }
    }
    app?.canvas?.setDirty?.(true, true);
}

app.registerExtension({
    name: "Comfy.PromptAdherenceEnhancerPro.ModelDetection",

    setup() {
        // Renderer switching can happen without a browser reload. Rebuild the
        // read-only display in the active renderer when that setting changes.
        app?.ui?.settings?.addEventListener?.("Comfy.VueNodes.Enabled.change", refreshAllNodes);
    },

    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== NODE_NAME) return;

        const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            originalOnNodeCreated?.apply(this, arguments);
            this.properties = this.properties ?? {};
            applyRendererLayout(this);
            restoreSavedDetection(this);
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
            app?.canvas?.setDirty?.(true, true);
        };

        const originalOnConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            originalOnConfigure?.apply(this, arguments);
            this.properties = this.properties ?? {};
            applyRendererLayout(this);
            restoreSavedDetection(this);
        };

        const originalOnDrawForeground = nodeType.prototype.onDrawForeground;
        nodeType.prototype.onDrawForeground = function (ctx) {
            originalOnDrawForeground?.apply(this, arguments);
            drawClassicDetectionPanel(this, ctx);
        };
    },
});
