import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { mkdtemp, readFile, writeFile, mkdir, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { resolve, extname, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const args = process.argv.slice(2);
const output = resolve(
	root,
	args.includes("--output") ? args[args.indexOf("--output") + 1] : "proof/site",
);
await mkdir(output, { recursive: true });
const delay = (ms) => new Promise((done) => setTimeout(done, ms));
let server;
let url = args.includes("--url") ? args[args.indexOf("--url") + 1] : null;
if (!url) {
	server = createServer(async (req, res) => {
		try {
			const pathname = decodeURIComponent(
				new URL(req.url, "http://localhost").pathname,
			);
			const path = resolve(
				root,
				"website",
				`.${pathname === "/" ? "/index.html" : pathname}`,
			);
			if (!path.startsWith(`${root}/website/`)) {
				res.writeHead(403).end();
				return;
			}
			const body = await readFile(path);
			res.setHeader(
				"Content-Type",
				{
					".html": "text/html",
					".js": "text/javascript",
					".css": "text/css",
					".json": "application/json",
					".txt": "text/plain",
				}[extname(path)] || "application/octet-stream",
			);
			res.end(body);
		} catch {
			res.writeHead(404).end();
		}
	});
	await new Promise((done) => server.listen(0, "127.0.0.1", done));
	url = `http://127.0.0.1:${server.address().port}/`;
}

async function browser(enabled) {
	const profile = await mkdtemp(resolve(tmpdir(), "jev-chrome-"));
	const chrome = spawn(
		process.env.CHROME || "/usr/bin/google-chrome",
		[
			"--headless=new",
			"--no-sandbox",
			"--disable-dev-shm-usage",
			"--remote-debugging-port=0",
			`--user-data-dir=${profile}`,
			`${enabled ? "--enable" : "--disable"}-features=WebMCP`,
			"about:blank",
		],
		{ stdio: ["ignore", "ignore", "pipe"] },
	);
	let stderr = "";
	chrome.stderr.on("data", (chunk) => {
		stderr += chunk;
	});
	let websocket;
	try {
		for (let i = 0; i < 200; i++) {
			try {
				const [port] = (
					await readFile(resolve(profile, "DevToolsActivePort"), "utf8")
				).split("\n");
				const targets = await (
					await fetch(`http://127.0.0.1:${port}/json/list`)
				).json();
				websocket = targets.find(
					(item) => item.type === "page",
				)?.webSocketDebuggerUrl;
				if (websocket) break;
			} catch {
				/* Chrome is starting. */
			}
			if (chrome.exitCode !== null) throw new Error(`Chrome exited: ${stderr}`);
			await delay(50);
		}
		assert.ok(websocket, `Chrome CDP startup failed: ${stderr}`);
		const ws = new WebSocket(websocket);
		await new Promise((done, reject) => {
			ws.addEventListener("open", done, { once: true });
			ws.addEventListener("error", reject, { once: true });
		});
		let sequence = 0;
		const pending = new Map();
		const errors = [];
		ws.addEventListener("message", ({ data }) => {
			const message = JSON.parse(data);
			if (message.id) {
				const item = pending.get(message.id);
				if (!item) return;
				pending.delete(message.id);
				clearTimeout(item.timer);
				if (message.error)
					item.reject(new Error(JSON.stringify(message.error)));
				else item.done(message.result);
			} else if (message.method === "Runtime.exceptionThrown")
				errors.push(message.params.exceptionDetails);
			else if (
				message.method === "Log.entryAdded" &&
				message.params.entry.level === "error"
			)
				errors.push(message.params.entry);
		});
		function cdp(method, params = {}) {
			return new Promise((done, reject) => {
				const id = ++sequence;
				const timer = setTimeout(() => {
					pending.delete(id);
					reject(new Error(`CDP timeout: ${method}`));
				}, 15000);
				pending.set(id, { done, reject, timer });
				ws.send(JSON.stringify({ id, method, params }));
			});
		}
		async function evaluate(expression) {
			const result = await cdp("Runtime.evaluate", {
				expression,
				awaitPromise: true,
				returnByValue: true,
				userGesture: true,
			});
			if (result.exceptionDetails)
				throw new Error(JSON.stringify(result.exceptionDetails));
			return result.result.value;
		}
		await cdp("Runtime.enable");
		await cdp("Log.enable");
		await cdp("Page.enable");
		await cdp("Page.navigate", { url });
		for (let i = 0; i < 200; i++) {
			if (
				await evaluate(
					"document.readyState === 'complete' && document.querySelectorAll('#results-body tr').length > 0",
				)
			)
				break;
			await delay(50);
		}
		assert.ok(
			await evaluate(
				"document.querySelectorAll('#results-body tr').length > 0",
			),
			"Published result rows must finish loading",
		);
		const result = {
			enabled,
			url,
			tools: [],
			interactions: [],
			screenshots: [],
			errors,
		};
		if (enabled) {
			for (let i = 0; i < 100; i++) {
				result.tools = await evaluate(
					"(async () => document.modelContext?.getTools ? (await document.modelContext.getTools()).map(tool => ({name:tool.name,description:tool.description})) : [])()",
				);
				if (result.tools.length >= 5) break;
				await delay(50);
			}
			assert.deepEqual(
				result.tools.map((tool) => tool.name).toSorted(),
				["describe", "get_results", "list_runs", "select_run", "set_metric"],
				"Native getTools must list every page tool; absent tools are NOT PROVED",
			);
			async function execute(name, input) {
				const value = await evaluate(
					`(async () => { const tool = (await document.modelContext.getTools()).find(tool => tool.name === ${JSON.stringify(name)}); return document.modelContext.executeTool(tool, ${JSON.stringify(JSON.stringify(input))}); })()`,
				);
				result.interactions.push({ name, input, result: value });
				let parsed = value;
				if (typeof parsed === "string") parsed = JSON.parse(parsed);
				if (parsed?.content)
					parsed = JSON.parse(
						parsed.content.find((item) => item.type === "text").text,
					);
				assert.equal(parsed.ok, true, `${name} must return success`);
				return parsed.data;
			}
			await execute("describe", {});
			const runs = await execute("list_runs", {});
			assert.ok(runs.length > 0);
			await execute("get_results", {});
			async function visibleMatches(snapshot) {
				const visible = await evaluate(
					`({run_id:document.getElementById('run-picker').value,title:document.getElementById('run-title').textContent,metric:document.querySelector('[data-metric][aria-pressed="true"]').dataset.metric,rows:document.querySelectorAll('#results-body tr').length,chartValues:[...document.querySelectorAll('.bar-value')].map(el=>el.textContent.trim())})`,
				);
				assert.equal(visible.run_id, snapshot.run_id);
				assert.equal(visible.title, snapshot.title);
				assert.equal(visible.metric, snapshot.metric);
				assert.equal(visible.rows, snapshot.models.length);
				assert.deepEqual(
					visible.chartValues,
					snapshot.models.map(
						(model) =>
							`${Number.isFinite(model[snapshot.metric]) ? model[snapshot.metric].toFixed(1) : "—"} ms`,
					),
				);
				result.interactions.push({ visible });
			}
			for (const run of runs) {
				const selected = await execute("select_run", { run_id: run.id });
				assert.equal(selected.run_id, run.id);
				const snapshot = await execute("get_results", {});
				assert.equal(snapshot.run_id, run.id);
				await visibleMatches(snapshot);
			}
			for (const metric of ["mean_ms", "p95_ms", "median_ms"]) {
				const updated = await execute("set_metric", { metric });
				assert.equal(updated.metric, metric);
				const snapshot = await execute("get_results", {});
				assert.equal(snapshot.metric, metric);
				await visibleMatches(snapshot);
			}
			const beforeInvalid = await execute("get_results", {});
			async function rejectInput(name, rawInput) {
				const value = await evaluate(
					`(async () => { try { const tool = (await document.modelContext.getTools()).find(tool => tool.name === ${JSON.stringify(name)}); return await document.modelContext.executeTool(tool, ${JSON.stringify(rawInput)}); } catch (error) { return {native_rejected:true,error:String(error)}; } })()`,
				);
				let parsed = value;
				if (typeof parsed === "string") parsed = JSON.parse(parsed);
				if (parsed?.content)
					parsed = JSON.parse(
						parsed.content.find((item) => item.type === "text").text,
					);
				assert.ok(
					parsed.native_rejected === true ||
						(parsed.ok === false &&
							parsed.data === null &&
							typeof parsed.error === "string"),
					`${name} must reject ${rawInput}`,
				);
				result.interactions.push({
					name,
					rejected_input: rawInput,
					result: parsed,
				});
			}
			for (const name of ["describe", "list_runs", "get_results"]) {
				for (const raw of [
					"{",
					"[]",
					"null",
					"1",
					'"wrong type"',
					'{"extra":true}',
				])
					await rejectInput(name, raw);
			}
			for (const [name, inputs] of [
				[
					"select_run",
					[
						{},
						[],
						{ run_id: "missing" },
						{ run_id: 1 },
						{ run_id: runs[0].id, extra: true },
					],
				],
				[
					"set_metric",
					[
						{},
						[],
						{ metric: "p99_ms" },
						{ metric: 1 },
						{ metric: "median_ms", extra: true },
					],
				],
			])
				for (const input of inputs)
					await rejectInput(name, JSON.stringify(input));
			assert.deepEqual(
				await execute("get_results", {}),
				beforeInvalid,
				"Invalid native inputs must leave selected run and metric unchanged",
			);
			await visibleMatches(beforeInvalid);
		} else {
			result.nativeAvailable = await evaluate(
				"Boolean(document.modelContext?.getTools)",
			);
			assert.equal(
				result.nativeAvailable,
				false,
				"Feature-disabled proof must have no native registry",
			);
			result.visibleControls = await evaluate(
				"[...document.querySelectorAll('select,button,input')].filter(el => el.getBoundingClientRect().width > 0).length",
			);
			assert.ok(
				result.visibleControls >= 2,
				"Human controls must remain rendered",
			);
		}
		for (const [label, width, height] of [
			["desktop", 1440, 1000],
			["mobile", 390, 844],
		]) {
			await cdp("Emulation.setDeviceMetricsOverride", {
				width,
				height,
				deviceScaleFactor: 1,
				mobile: label === "mobile",
			});
			await delay(150);
			const dimensions = await evaluate(
				"({scroll:document.documentElement.scrollWidth,client:document.documentElement.clientWidth})",
			);
			assert.ok(
				dimensions.scroll <= dimensions.client,
				`${label} horizontal overflow: ${JSON.stringify(dimensions)}`,
			);
			const screenshot = await cdp("Page.captureScreenshot", {
				format: "png",
				captureBeyondViewport: true,
			});
			const name = `${enabled ? "native" : "fallback"}-${label}.png`;
			await writeFile(
				resolve(output, name),
				Buffer.from(screenshot.data, "base64"),
			);
			result.screenshots.push(name);
		}
		assert.equal(errors.length, 0, `Browser errors: ${JSON.stringify(errors)}`);
		ws.close();
		return result;
	} finally {
		chrome.kill("SIGTERM");
		await Promise.race([
			new Promise((done) => chrome.once("exit", done)),
			delay(2000),
		]);
		if (chrome.exitCode === null) chrome.kill("SIGKILL");
		await rm(profile, {
			recursive: true,
			force: true,
			maxRetries: 5,
			retryDelay: 100,
		});
	}
}
const report = {
	timestamp: new Date().toISOString(),
	passed: false,
	modes: [],
};
try {
	report.modes.push(await browser(true));
	report.modes.push(await browser(false));
	report.passed = true;
} catch (error) {
	report.error = error.stack;
	process.exitCode = 1;
} finally {
	if (server) await new Promise((done) => server.close(done));
}
await writeFile(
	resolve(output, "proof.json"),
	`${JSON.stringify(report, null, 2)}\n`,
);
console.log(
	JSON.stringify({
		passed: report.passed,
		report: resolve(output, "proof.json"),
		error: report.error,
	}),
);
