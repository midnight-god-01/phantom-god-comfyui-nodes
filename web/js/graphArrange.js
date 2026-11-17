import { app } from "../../scripts/app.js";

const EXTENSION_NAME = "PhantomGod.AutoArrangeGraph";
const VERSION = "1.5.2";
const MARGIN = 50;
const FALLBACK_TITLE_HEIGHT = 30;

function getActiveGraph(canvas) {
    // The canvas graph is authoritative, including when a subgraph is open.
    return canvas?.graph ?? app.rootGraphOrUndefined ?? app.rootGraph ?? app.graph ?? null;
}

function getNodeSize(node) {
    const width = Number(node?.size?.[0]);
    const height = Number(node?.size?.[1]);

    return {
        width: Number.isFinite(width) && width > 0 ? width : 180,
        height: Number.isFinite(height) && height > 0 ? height : 100,
    };
}

function getNodeTitleHeight() {
    const titleHeight = Number(globalThis.LiteGraph?.NODE_TITLE_HEIGHT);
    return Number.isFinite(titleHeight) && titleHeight > 0
        ? titleHeight
        : FALLBACK_TITLE_HEIGHT;
}

function arrangeFloatLeft(canvas) {
    const graph = getActiveGraph(canvas);
    if (!graph || typeof graph.arrange !== "function") {
        console.warn(`[${EXTENSION_NAME}] The active graph does not expose arrange().`);
        return;
    }

    try {
        // Delegate to ComfyUI's native execution-order layout.
        graph.arrange();
    } catch (error) {
        console.error(`[${EXTENSION_NAME}] Float-left arrangement failed.`, error);
    }
}

function getOutgoingNodeIds(graph) {
    const outgoing = new Map();
    const links = graph?.links;

    // Current ComfyUI stores graph links in a Map. Use its public iterator rather
    // than the deprecated links[id] compatibility accessor or slot link mirrors.
    if (!links || typeof links.values !== "function") return outgoing;

    for (const link of links.values()) {
        if (link?.origin_id == null || link?.target_id == null) continue;

        let targets = outgoing.get(link.origin_id);
        if (!targets) {
            targets = [];
            outgoing.set(link.origin_id, targets);
        }
        targets.push(link.target_id);
    }

    return outgoing;
}

function moveNodesToFirstUseLevel(graph, orderedNodes) {
    const outgoing = getOutgoingNodeIds(graph);

    // Walk the topological order backwards. A node belongs immediately before
    // its earliest downstream consumer, matching the original Auto Arrange
    // float-right behavior while reading links through the current Map API.
    for (let index = orderedNodes.length - 1; index >= 0; index -= 1) {
        const node = orderedNodes[index];
        const targets = outgoing.get(node.id) ?? [];
        let firstUseLevel = Number.POSITIVE_INFINITY;

        for (const targetId of targets) {
            const targetNode = graph.getNodeById?.(targetId);
            const targetLevel = Number(targetNode?._level);
            if (Number.isFinite(targetLevel)) {
                firstUseLevel = Math.min(firstUseLevel, targetLevel - 1);
            }
        }

        if (Number.isFinite(firstUseLevel)) {
            node._level = firstUseLevel;
        }
    }
}

function arrangeFloatRight(canvas) {
    const graph = getActiveGraph(canvas);
    if (
        !graph ||
        typeof graph.computeExecutionOrder !== "function" ||
        typeof graph.getNodeById !== "function" ||
        typeof graph.setDirtyCanvas !== "function"
    ) {
        console.warn(`[${EXTENSION_NAME}] The active graph does not expose the required layout APIs.`);
        return;
    }

    try {
        // ComfyUI calculates topological execution order and writes node._level.
        const orderedNodes = graph.computeExecutionOrder(false, true);
        if (!Array.isArray(orderedNodes) || orderedNodes.length === 0) return;

        moveNodesToFirstUseLevel(graph, orderedNodes);

        const columns = new Map();
        for (const node of orderedNodes) {
            if (!node) continue;
            const level = node._level || 1;
            if (!columns.has(level)) columns.set(level, []);
            columns.get(level).push(node);
        }

        const titleHeight = getNodeTitleHeight();
        const sortedLevels = [...columns.keys()].sort((a, b) => a - b);
        let x = MARGIN;

        for (const level of sortedLevels) {
            const column = columns.get(level);
            if (!column?.length) continue;

            // Preserve the upstream ordering: image output nodes first, then
            // nodes with fewer inputs and outputs.
            column.sort((a, b) => {
                const aIsOutput = a.type === "SaveImage" || a.type === "PreviewImage";
                const bIsOutput = b.type === "SaveImage" || b.type === "PreviewImage";
                const outputDifference = Number(!aIsOutput) - Number(!bIsOutput);
                if (outputDifference !== 0) return outputDifference;

                const inputDifference = (a.inputs?.length ?? 0) - (b.inputs?.length ?? 0);
                if (inputDifference !== 0) return inputDifference;

                return (a.outputs?.length ?? 0) - (b.outputs?.length ?? 0);
            });

            const sizes = column.map(getNodeSize);
            const columnWidth = Math.max(100, ...sizes.map((size) => size.width));
            let y = MARGIN + titleHeight;

            column.forEach((node, index) => {
                const size = sizes[index];
                if (typeof node.setPos !== "function") {
                    throw new TypeError(`Node ${node.id ?? node.type ?? "unknown"} does not expose setPos().`);
                }

                // Right-align nodes within the column and retain the original
                // increasing vertical gap used by the upstream implementation.
                node.setPos(x + columnWidth - size.width, y);
                y += size.height + MARGIN + titleHeight + index;
            });

            x += columnWidth + MARGIN;
        }

        graph.setDirtyCanvas(true, true);
    } catch (error) {
        console.error(`[${EXTENSION_NAME}] Float-right arrangement failed.`, error);
    }
}

app.registerExtension({
    name: EXTENSION_NAME,

    // Official ComfyUI extension hook for the empty-canvas context menu.
    getCanvasMenuItems(canvas) {
        return [
            {
                content: "Arrange (float left)",
                callback: () => arrangeFloatLeft(canvas),
            },
            {
                content: "Arrange (float right)",
                callback: () => arrangeFloatRight(canvas),
            },
        ];
    },
});

console.info(`[Phantom God] Auto Arrange Graph extension loaded (v${VERSION}).`);
