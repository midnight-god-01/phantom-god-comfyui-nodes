import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { runInNewContext } from "node:vm";
import test from "node:test";

const source = await readFile(new URL("../web/js/graphArrange.js", import.meta.url), "utf8");
const entryImport = /^import\s+\{\s*app\s*\}\s+from\s+["']\.\.\/\.\.\/scripts\/app\.js["'];?\s*/m;

function loadExtension() {
    const script = source.replace(entryImport, "");
    assert.notEqual(script, source, "expected to find and replace the ComfyUI app import");

    const extensions = [];
    const context = {
        app: {
            get graph() {
                throw new Error("The deprecated ComfyApp.graph getter must not be accessed.");
            },
            get rootGraph() {
                throw new Error("Canvas actions must use the active canvas graph.");
            },
            registerExtension(extension) {
                extensions.push(extension);
            },
        },
        LiteGraph: { NODE_TITLE_HEIGHT: 30 },
        console: { info() {}, warn() {}, error() {} },
    };

    runInNewContext(script, context, { filename: "graphArrange.js" });
    assert.equal(extensions.length, 1, "the script should register exactly one extension");
    return extensions[0];
}

function makeNode(id, type, level, width, height, inputCount = 1, outputCount = 1) {
    let position = [0, 0];
    return {
        id,
        type,
        _level: level,
        size: [width, height],
        inputs: Array.from({ length: inputCount }),
        outputs: Array.from({ length: outputCount }),
        get pos() { return position; },
        setPos(x, y) { position = [x, y]; },
    };
}

function makeGraph(nodes, links = []) {
    const dirtyCalls = [];
    const byId = new Map(nodes.map((node) => [node.id, node]));
    return {
        links: new Map(links.map((link, index) => [index + 1, link])),
        dirtyCalls,
        computeCalls: [],
        computeExecutionOrder(onlyOnExecute, setLevel) {
            this.computeCalls.push([onlyOnExecute, setLevel]);
            return nodes;
        },
        getNodeById(id) { return byId.get(id); },
        setDirtyCanvas(...args) { dirtyCalls.push(args); },
    };
}

test("registers only the two canvas arrange commands", () => {
    const extension = loadExtension();
    const graph = { arrange() {}, computeExecutionOrder() { return []; } };
    const items = extension.getCanvasMenuItems({ graph });

    assert.deepEqual(Array.from(items, (item) => item.content), [
        "Arrange (float left)",
        "Arrange (float right)",
    ]);
    assert.ok(items.every((item) => typeof item.callback === "function"));
});


test("uses the active canvas graph without accessing deprecated app graph getters", () => {
    const extension = loadExtension();
    const activeSubgraph = {
        calls: 0,
        arrange() { this.calls += 1; },
    };
    const [floatLeft] = extension.getCanvasMenuItems({ graph: activeSubgraph });

    floatLeft.callback();

    assert.equal(activeSubgraph.calls, 1);
});

test("float-left delegates to ComfyUI's native graph arrange method", () => {
    const extension = loadExtension();
    const graph = { calls: 0, arrange() { this.calls += 1; } };
    const [floatLeft] = extension.getCanvasMenuItems({ graph });

    floatLeft.callback();
    assert.equal(graph.calls, 1);
});

test("float-right uses execution levels, output ordering, and right alignment", () => {
    const extension = loadExtension();
    const sourceNode = makeNode(1, "CheckpointLoaderSimple", 1, 180, 100, 0, 1);
    const processNode = makeNode(2, "KSampler", 2, 220, 160, 3, 1);
    const saveNode = makeNode(3, "SaveImage", 3, 120, 90, 2, 0);
    const previewNode = makeNode(4, "PreviewImage", 3, 180, 100, 1, 0);
    const nodes = [sourceNode, processNode, saveNode, previewNode];
    const graph = makeGraph(nodes);
    const [, floatRight] = extension.getCanvasMenuItems({ graph });

    floatRight.callback();

    assert.deepEqual(graph.computeCalls, [[false, true]]);
    assert.ok(sourceNode.pos[0] < processNode.pos[0]);
    assert.ok(processNode.pos[0] < previewNode.pos[0]);
    assert.equal(previewNode.pos[1], 80, "the PreviewImage with fewer inputs should sort first");
    assert.ok(saveNode.pos[1] > previewNode.pos[1]);
    assert.ok(saveNode.pos[0] > previewNode.pos[0], "narrow nodes should be right-aligned");
    assert.deepEqual(Array.from(graph.dirtyCalls[0]), [true, true]);
});

test("float-right moves a node to the column of its earliest downstream use", () => {
    const extension = loadExtension();
    const branchSource = makeNode(1, "BranchSource", 4, 200, 100, 1, 2);
    const earlyConsumer = makeNode(2, "PreviewImage", 2, 150, 90, 1, 0);
    const lateConsumer = makeNode(3, "SaveImage", 5, 150, 90, 1, 0);
    const nodes = [branchSource, earlyConsumer, lateConsumer];
    const graph = makeGraph(nodes, [
        { origin_id: 1, target_id: 2 },
        { origin_id: 1, target_id: 3 },
    ]);
    const [, floatRight] = extension.getCanvasMenuItems({ graph });

    floatRight.callback();

    assert.equal(branchSource._level, 1, "the earliest consumer determines the upstream column");
    assert.equal(branchSource.pos[0], 50);
    assert.ok(earlyConsumer.pos[0] > branchSource.pos[0]);
    assert.ok(lateConsumer.pos[0] > branchSource.pos[0]);
});

test("float-right preserves the zero execution level created for earliest downstream use", () => {
    const extension = loadExtension();
    const upstream = makeNode(1, "Upstream", 4, 200, 100, 1, 1);
    const firstUse = makeNode(2, "PreviewImage", 1, 150, 90, 1, 0);
    const graph = makeGraph([upstream, firstUse], [
        { origin_id: 1, target_id: 2 },
    ]);
    const [, floatRight] = extension.getCanvasMenuItems({ graph });

    floatRight.callback();

    assert.equal(upstream._level, 0);
    assert.equal(firstUse._level, 1);
    assert.ok(upstream.pos[0] < firstUse.pos[0], "level zero must remain a separate upstream column");
});

test("float-right safely does nothing for an empty graph", () => {
    const extension = loadExtension();
    const graph = makeGraph([]);
    const [, floatRight] = extension.getCanvasMenuItems({ graph });

    assert.doesNotThrow(() => floatRight.callback());
    assert.equal(graph.dirtyCalls.length, 0, "an empty graph should not need a redraw");
});
