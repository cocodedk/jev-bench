// Prove website/test-sets.html in Chrome with native WebMCP: every tool must be listed by getTools() and answer
// through executeTool; screenshots at desktop and mobile width. Writes proof/test-sets/proof.json.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, extname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const output = resolve(root, "proof/test-sets");
await mkdir(output, { recursive: true });
const delay = (ms) => new Promise((done) => setTimeout(done, ms));
const types = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json" };
const server = createServer(async (req, res) => {
	const path = resolve(root, "website", `.${decodeURIComponent(new URL(req.url, "http://x").pathname)}`);
	try {
		if (!path.startsWith(`${root}/website/`)) throw new Error("outside");
		res.setHeader("Content-Type", types[extname(path)] || "application/octet-stream");
		res.end(await readFile(path));
	} catch {
		res.writeHead(404).end();
	}
});
await new Promise((done) => server.listen(0, "127.0.0.1", done));
const url = `http://127.0.0.1:${server.address().port}/test-sets.html`;
const profile = await mkdtemp(resolve(tmpdir(), "jev-chrome-"));
const chrome = spawn(process.env.CHROME || "/usr/bin/google-chrome", ["--headless=new", "--no-sandbox", "--disable-dev-shm-usage",
	"--remote-debugging-port=0", `--user-data-dir=${profile}`, "--enable-features=WebMCP", "about:blank"], { stdio: "ignore" });
let socketUrl;
for (let i = 0; i < 200 && !socketUrl; i++) {
	try {
		const [port] = (await readFile(resolve(profile, "DevToolsActivePort"), "utf8")).split("\n");
		socketUrl = (await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find((t) => t.type === "page")?.webSocketDebuggerUrl;
	} catch {
		await delay(50);
	}
}
const ws = new WebSocket(socketUrl);
await new Promise((done) => ws.addEventListener("open", done, { once: true }));
let sequence = 0;
const pending = new Map();
const errors = [];
ws.addEventListener("message", ({ data }) => {
	const message = JSON.parse(data);
	if (message.id) pending.get(message.id)?.(message);
	else if (message.method === "Runtime.exceptionThrown") errors.push(message.params.exceptionDetails.text);
});
const cdp = (method, params = {}) => new Promise((done, reject) => {
	const id = ++sequence;
	pending.set(id, (m) => (m.error ? reject(new Error(JSON.stringify(m.error))) : done(m.result)));
	ws.send(JSON.stringify({ id, method, params }));
});
const evaluate = async (expression) => {
	const result = await cdp("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true, userGesture: true });
	if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
	return result.result.value;
};
const proof = { url, tools: [], interactions: [], screenshots: [], errors };
try {
	await cdp("Runtime.enable");
	await cdp("Page.navigate", { url });
	for (let i = 0; i < 100 && proof.tools.length < 3; i++) {
		await delay(50);
		proof.tools = await evaluate("(async () => document.modelContext?.getTools ? (await document.modelContext.getTools()).map(t => t.name) : [])()");
	}
	assert.deepEqual(proof.tools.toSorted(), ["describe", "get_test_set", "list_test_sets"], "getTools must list every tool; a missing tool is NOT PROVED");
	const call = async (name, input) => {
		let value = await evaluate(`(async () => { const tool = (await document.modelContext.getTools()).find(t => t.name === ${JSON.stringify(name)}); return document.modelContext.executeTool(tool, ${JSON.stringify(input)}); })()`);
		if (typeof value === "string") value = JSON.parse(value);
		if (value?.content) value = JSON.parse(value.content.find((item) => item.type === "text").text);
		proof.interactions.push({ name, input, ok: value.ok, error: value.error });
		return value;
	};
	const sets = (await call("list_test_sets", {})).data;
	assert.deepEqual(sets.map((set) => set.id), ["decisions-choice", "decisions-noul", "decisions-score"]);
	assert.equal((await call("describe", {})).data.sets.length, 3);
	const rows = await evaluate("document.querySelectorAll('tbody tr').length");
	let cases = 0;
	for (const set of sets) {
		const full = await call("get_test_set", { set_id: set.id });
		assert.equal(full.data.cases.length, set.cases);
		cases += set.cases;
	}
	assert.equal(rows, cases, "every case the tools serve is a row on the page");
	assert.equal((await call("get_test_set", { set_id: "nope" })).error, "unknown_set");
	assert.equal((await call("get_test_set", {})).error, "invalid_input");
	for (const [name, width, height, mobile] of [["desktop", 1280, 900, false], ["mobile", 390, 844, true]]) {
		await cdp("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile });
		await delay(200);
		assert.ok(await evaluate("document.documentElement.scrollWidth <= innerWidth"), `${name}: no horizontal page scroll`);
		const file = resolve(output, `${name}.png`);
		await writeFile(file, Buffer.from((await cdp("Page.captureScreenshot", { format: "png" })).data, "base64"));
		proof.screenshots.push(file);
	}
	assert.deepEqual(errors, [], "no page errors");
	proof.passed = true;
} finally {
	await writeFile(resolve(output, "proof.json"), `${JSON.stringify(proof, null, 2)}\n`);
	ws.close();
	const exited = new Promise((done) => chrome.once("exit", done));
	chrome.kill();
	await exited;
	server.close();
	await rm(profile, { recursive: true, force: true });
}
console.log(`PROVED ${proof.tools.length} tools, ${proof.interactions.length} calls, ${proof.screenshots.length} screenshots`);
