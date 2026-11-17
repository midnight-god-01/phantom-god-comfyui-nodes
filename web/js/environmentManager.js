import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const EXTENSION_NAME = "PhantomGod.EnvironmentManager";
const NODE_TYPE = "PhantomGodEnvironmentManager";
const WIDGET_NAME = "phantom_god_environment_manager";

function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
}

function button(label, className, callback) {
    const item = element("button", className, label);
    item.type = "button";
    item.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        callback();
    });
    return item;
}

function injectStyles() {
    if (document.getElementById("phantom-god-environment-style")) return;
    const style = document.createElement("style");
    style.id = "phantom-god-environment-style";
    style.textContent = [
        ".pg-env-root{display:flex;flex-direction:column;gap:9px;width:100%;box-sizing:border-box;color:var(--input-text,#eee);font:12px Inter,system-ui,sans-serif;}",
        ".pg-env-root *{box-sizing:border-box;}",
        ".pg-env-heading{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:2px 1px 5px;}",
        ".pg-env-kicker{color:var(--descrip-text,#999);font-size:10px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;}",
        ".pg-env-title{font-size:15px;font-weight:700;letter-spacing:.01em;}",
        ".pg-env-button{min-height:30px;padding:6px 10px;border:1px solid var(--border-color,rgba(255,255,255,.16));border-radius:5px;background:var(--comfy-input-bg,#282828);color:var(--input-text,#eee);font:600 11px Inter,system-ui,sans-serif;cursor:pointer;transition:background .14s,border-color .14s;}",
        ".pg-env-button:hover:not(:disabled){border-color:var(--p-primary,#8b9b9b);background:var(--comfy-menu-bg,#383838);}",
        ".pg-env-button:disabled{opacity:.45;cursor:not-allowed;}",
        ".pg-env-primary{border-color:rgba(110,170,155,.45);background:rgba(70,130,115,.15);}",
        ".pg-env-check{white-space:nowrap;}",
        ".pg-env-panel{display:flex;flex-direction:column;gap:7px;padding:10px;border:1px solid var(--border-color,rgba(255,255,255,.13));border-radius:6px;background:rgba(255,255,255,.025);}",
        ".pg-env-panel-head{display:flex;align-items:center;justify-content:space-between;gap:8px;}",
        ".pg-env-name{font-size:13px;font-weight:700;}",
        ".pg-env-status{flex:0 0 auto;padding:3px 7px;border:1px solid rgba(255,255,255,.14);border-radius:4px;color:var(--descrip-text,#aaa);font:10px Inter,system-ui,sans-serif;}",
        ".pg-env-status.ok{border-color:rgba(90,180,125,.38);background:rgba(50,130,80,.13);color:#a7d9b6;}",
        ".pg-env-status.warn{border-color:rgba(220,165,75,.38);background:rgba(160,110,35,.12);color:#e5c58c;}",
        ".pg-env-status.bad{border-color:rgba(220,95,80,.38);background:rgba(150,45,35,.12);color:#e5a49c;}",
        ".pg-env-message{color:var(--descrip-text,#aaa);font-size:11px;line-height:1.45;overflow-wrap:anywhere;}",
        ".pg-env-meta{display:grid;grid-template-columns:1fr 1fr;gap:5px 12px;}",
        ".pg-env-meta-item{min-width:0;}",
        ".pg-env-meta-label{display:block;margin-bottom:2px;color:var(--descrip-text,#888);font-size:9px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;}",
        ".pg-env-meta-value{display:block;color:var(--input-text,#ddd);font-size:11px;overflow-wrap:anywhere;}",
        ".pg-env-path{padding:7px 8px;border-radius:4px;background:rgba(0,0,0,.14);color:var(--descrip-text,#aaa);font:10px ui-monospace,monospace;overflow-wrap:anywhere;}",
        ".pg-env-actions{display:flex;gap:6px;}",
        ".pg-env-actions .pg-env-button{flex:1;}",
        ".pg-env-note{padding:8px 9px;border-left:2px solid var(--border-color,rgba(255,255,255,.2));background:rgba(255,255,255,.025);color:var(--descrip-text,#999);font-size:10px;line-height:1.45;}",
        ".pg-env-job{padding:9px;border:1px solid rgba(110,170,155,.25);border-radius:5px;background:rgba(70,130,115,.08);}",
        ".pg-env-job-title{font-size:11px;font-weight:700;}",
        ".pg-env-job-message{margin-top:4px;color:var(--descrip-text,#aaa);font-size:10px;line-height:1.4;overflow-wrap:anywhere;}",
        ".pg-env-log{max-height:130px;margin-top:7px;padding:7px;border-radius:4px;background:rgba(0,0,0,.2);color:var(--descrip-text,#aaa);font:9px/1.4 ui-monospace,monospace;white-space:pre-wrap;overflow:auto;}",
        ".pg-env-error{color:#e59b91;}",
    ].join("");
    document.head.appendChild(style);
}

function statusClass(status) {
    const value = String(status || "").toLowerCase();
    if (value === "up to date" || value === "completed") return "ok";
    if (value.includes("not installed") || value.includes("update") || value.includes("compatible") || value.includes("index unavailable")) return "warn";
    if (value.includes("blocked") || value.includes("unsupported") || value.includes("failed") || value.includes("conflict") || value.includes("import failed")) return "bad";
    return "";
}

function metaItem(label, value) {
    const wrapper = element("div", "pg-env-meta-item");
    wrapper.appendChild(element("span", "pg-env-meta-label", label));
    wrapper.appendChild(element("span", "pg-env-meta-value", value || "Not detected"));
    return wrapper;
}

function renderEnvironment(report) {
    const panel = element("section", "pg-env-panel");
    panel.appendChild(element("div", "pg-env-name", "ComfyUI Python environment"));
    if (!report?.environment) {
        panel.appendChild(element("div", "pg-env-message", "Select Check Environment to inspect the active ComfyUI runtime."));
        return panel;
    }
    const env = report.environment;
    const grid = element("div", "pg-env-meta");
    grid.appendChild(metaItem("Python", env.python));
    grid.appendChild(metaItem("PyTorch", env.torch));
    grid.appendChild(metaItem("pip", env.pip_available ? (env.pip_version || "Available") : "Not available"));
    grid.appendChild(metaItem("Torch CUDA runtime", env.cuda));
    grid.appendChild(metaItem("CUDA available", env.cuda_available ? "Yes" : "No"));
    grid.appendChild(metaItem("GPU", env.gpu_name));
    grid.appendChild(metaItem("Compute capability", Array.isArray(env.capability) ? env.capability.join(".") : null));
    grid.appendChild(metaItem("NVIDIA driver", env.driver));
    grid.appendChild(metaItem("Platform", env.system + " / " + env.machine));
    panel.appendChild(grid);
    panel.appendChild(element("div", "pg-env-path", env.python_executable));
    if (env.error) panel.appendChild(element("div", "pg-env-message pg-env-error", env.error));
    return panel;
}

function renderPackage(node, key, title, report) {
    const info = report?.[key] || {};
    const panel = element("section", "pg-env-panel");
    const head = element("div", "pg-env-panel-head");
    head.appendChild(element("div", "pg-env-name", title));
    const status = element("span", "pg-env-status " + statusClass(info.status), info.status || "Not checked");
    head.appendChild(status);
    panel.appendChild(head);

    panel.appendChild(element("div", "pg-env-message", info.message || "Run an environment check to see compatibility."));
    if (info.triton_note) panel.appendChild(element("div", "pg-env-message", info.triton_note));
    const current = info.installed ? "Installed: " + info.installed : "Installed: no";
    const target = info.target_version || (info.latest ? "Latest compatible: " + info.latest : (info.target_minor ? "Compatible line: 3." + info.target_minor : "Compatible version: not determined"));
    panel.appendChild(element("div", "pg-env-message", current + "  ·  " + target));

    const actions = element("div", "pg-env-actions");
    actions.appendChild(button("Check", "pg-env-button", () => checkEnvironment(node)));
    const installLabel = info.installed ? "Update / Repair" : "Install";
    const install = button(installLabel, "pg-env-button pg-env-primary", () => installPackage(node, key));
    install.disabled = !info.supported || Boolean(node.__phantomGodEnvBusy);
    install.title = info.supported ? "Install a build selected for this environment" : "Resolve the environment compatibility blockers first";
    actions.appendChild(install);
    panel.appendChild(actions);
    return panel;
}

function render(node) {
    const root = node.__phantomGodEnvRoot;
    if (!root) return;
    root.replaceChildren();

    const heading = element("div", "pg-env-heading");
    const labels = element("div");
    labels.appendChild(element("div", "pg-env-kicker", "Phantom God  /  System Tools"));
    labels.appendChild(element("div", "pg-env-title", "Environment Manager"));
    heading.appendChild(labels);
    const checkAll = button(node.__phantomGodEnvBusy ? "Working…" : "Check All", "pg-env-button pg-env-check", () => checkEnvironment(node));
    checkAll.disabled = Boolean(node.__phantomGodEnvBusy);
    heading.appendChild(checkAll);
    root.appendChild(heading);

    const report = node.__phantomGodEnvReport;
    root.appendChild(renderEnvironment(report));
    root.appendChild(renderPackage(node, "triton", "TRITON", report));
    root.appendChild(renderPackage(node, "sageattention", "SAGE ATTENTION", report));

    const note = element(
        "div",
        "pg-env-note",
        "Installs into the Python executable shown above. Package dependencies and PyTorch are left unchanged. Restart ComfyUI after a successful installation."
    );
    root.appendChild(note);

    const job = node.__phantomGodEnvJob;
    if (job) {
        const box = element("div", "pg-env-job");
        const title = job.state === "completed" ? "Installation complete" :
            (job.state === "failed" ? "Installation failed" : "Installation in progress");
        box.appendChild(element("div", "pg-env-job-title", title + " · " + job.package));
        box.appendChild(element("div", "pg-env-job-message", job.message || job.state));
        if (job.output) box.appendChild(element("pre", "pg-env-log", job.output));
        root.appendChild(box);
    }

    if (node.__phantomGodEnvError) {
        root.appendChild(element("div", "pg-env-message pg-env-error", node.__phantomGodEnvError));
    }
    node.setDirtyCanvas?.(true, true);
}

async function checkEnvironment(node) {
    if (node.__phantomGodEnvBusy) return;
    node.__phantomGodEnvError = null;
    node.__phantomGodEnvBusy = true;
    render(node);
    try {
        const response = await api.fetchApi("/phantom_god/environment/check", { method: "POST" });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Environment check failed.");
        node.__phantomGodEnvReport = data;
    } catch (error) {
        node.__phantomGodEnvError = error?.message || String(error);
    } finally {
        node.__phantomGodEnvBusy = false;
        render(node);
    }
}

async function installPackage(node, packageName) {
    if (node.__phantomGodEnvBusy) return;
    node.__phantomGodEnvError = null;
    node.__phantomGodEnvBusy = true;
    node.__phantomGodEnvJob = { package: packageName, state: "queued", message: "Starting package installation." };
    render(node);
    try {
        const response = await api.fetchApi("/phantom_god/environment/install", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ package: packageName }),
        });
        const start = await response.json();
        if (!response.ok) throw new Error(start.error || "Could not start installation.");
        const jobId = start.job_id;
        let finished = false;
        for (let attempt = 0; attempt < 900; attempt += 1) {
            await new Promise((resolve) => setTimeout(resolve, 1500));
            const jobResponse = await api.fetchApi("/phantom_god/environment/job/" + encodeURIComponent(jobId));
            const job = await jobResponse.json();
            if (!jobResponse.ok) throw new Error(job.error || "Could not read installation status.");
            node.__phantomGodEnvJob = job;
            render(node);
            if (job.state === "completed" || job.state === "failed") {
                finished = true;
                break;
            }
        }
        if (!finished) throw new Error("Installation status polling stopped after 22.5 minutes. Check the ComfyUI console and pip output.");
        if (node.__phantomGodEnvJob.state === "completed") {
            const checkResponse = await api.fetchApi("/phantom_god/environment/check", { method: "POST" });
            const data = await checkResponse.json();
            if (checkResponse.ok) node.__phantomGodEnvReport = data;
        }
    } catch (error) {
        node.__phantomGodEnvError = error?.message || String(error);
    } finally {
        node.__phantomGodEnvBusy = false;
        render(node);
    }
}

function setupNode(node) {
    if (node.__phantomGodEnvRoot || typeof node.addDOMWidget !== "function") return;
    injectStyles();
    const root = element("div", "pg-env-root");
    node.__phantomGodEnvRoot = root;

    const widget = node.addDOMWidget(WIDGET_NAME, "phantom_god_environment_manager", root, {
        getValue: () => "",
        setValue: () => {},
        getMinHeight: () => 430,
        getMaxHeight: () => 900,
        margin: 5,
        serialize: false,
    });
    widget.computeLayoutSize = () => ({ minHeight: 430, minWidth: 390 });
    node.__phantomGodEnvWidget = widget;

    if (!node.size || node.size[0] < 390) {
        node.size = [430, Math.max(node.size?.[1] || 0, 440)];
    }
    render(node);
    checkEnvironment(node);
}

function patchNodeType(nodeType) {
    const prototype = nodeType?.prototype;
    if (!prototype || prototype.__phantomGodEnvPatched) return;
    const originalRemoved = prototype.onRemoved;
    prototype.onRemoved = function (...args) {
        this.__phantomGodEnvRoot?.remove?.();
        this.__phantomGodEnvRoot = null;
        return originalRemoved?.apply(this, args);
    };
    prototype.__phantomGodEnvPatched = true;
}

app.registerExtension({
    name: EXTENSION_NAME,
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData?.name === NODE_TYPE) patchNodeType(nodeType);
    },
    nodeCreated(node) {
        if (node?.type === NODE_TYPE || node?.comfyClass === NODE_TYPE) setupNode(node);
    },
});

console.info("[Phantom God] Environment Manager frontend loaded.");
