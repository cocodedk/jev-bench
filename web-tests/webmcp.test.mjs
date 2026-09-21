import assert from "node:assert/strict";
import { test } from "node:test";
import { registerPageTools } from "../website/webmcp.js";

const names = [
	"describe",
	"get_results",
	"list_runs",
	"select_run",
	"set_metric",
];
function fixture() {
	const calls = [];
	const controller = {
		describe: () => ({
			title: "Benchmark results",
			controls: ["run", "metric"],
		}),
		listRuns: () => [
			{ id: "a", title: "Run A" },
			{ id: "b", title: "Run B" },
		],
		getResults: () => ({ run_id: "a", rows: [] }),
		selectRun: (id) => {
			calls.push(["run", id]);
			return { run_id: id };
		},
		setMetric: (metric) => {
			calls.push(["metric", metric]);
			return { metric };
		},
	};
	return { calls, controller };
}
async function setup(controller = fixture().controller) {
	const tools = new Map();
	await registerPageTools(controller, {
		registerTool: (tool) => tools.set(tool.name, tool),
	});
	return tools;
}
function envelope(value, ok) {
	assert.deepEqual(Object.keys(value).toSorted(), ["data", "error", "ok"]);
	assert.equal(value.ok, ok);
	if (ok) assert.equal(value.error, null);
	else {
		assert.equal(typeof value.error, "string");
		assert.equal(value.data, null);
	}
}
let count = 0;
function check(name, fn) {
	count++;
	test(name, fn);
}
check(
	"registers exactly five tools with closed schemas and correct read-only hints",
	async () => {
		const tools = await setup();
		assert.deepEqual([...tools.keys()].toSorted(), names);
		for (const [name, tool] of tools) {
			assert.equal(typeof tool.description, "string");
			assert.ok(tool.description.length > 10);
			assert.equal(tool.inputSchema.type, "object");
			assert.equal(tool.inputSchema.additionalProperties, false);
			assert.equal(
				tool.annotations.readOnlyHint,
				!["select_run", "set_metric"].includes(name),
			);
			assert.equal(
				tool.annotations.untrustedContentHint,
				["get_results", "select_run", "set_metric"].includes(name),
			);
		}
	},
);
check(
	"absent registry leaves controls available without throwing",
	async () => {
		assert.deepEqual(await registerPageTools(fixture().controller, null), []);
	},
);
check(
	"registration failure does not prevent other tools registering",
	async () => {
		const attempted = [];
		await registerPageTools(fixture().controller, {
			registerTool(tool) {
				attempted.push(tool.name);
				if (tool.name === "describe") throw new Error("unavailable");
			},
		});
		assert.deepEqual(attempted.toSorted(), names);
	},
);
check("read tools return closed success envelopes", async () => {
	const tools = await setup();
	for (const name of ["describe", "get_results", "list_runs"])
		envelope(await tools.get(name).execute({}), true);
});
check(
	"all tools reject array, null, scalar and extra-property input",
	async () => {
		const tools = await setup();
		for (const tool of tools.values()) {
			for (const input of [null, [], "x", 4, { unexpected: true }])
				envelope(await tool.execute(input), false);
		}
	},
);
check("run selection accepts only IDs from the controller list", async () => {
	const { controller, calls } = fixture();
	const tools = await setup(controller);
	envelope(await tools.get("select_run").execute({ run_id: "b" }), true);
	for (const run_id of ["missing", "__proto__", 1, null, ["a"]])
		envelope(await tools.get("select_run").execute({ run_id }), false);
	envelope(
		await tools.get("select_run").execute({ run_id: "a", extra: true }),
		false,
	);
	assert.deepEqual(calls, [["run", "b"]]);
});
check("metric selection accepts exactly the published allowlist", async () => {
	const { controller, calls } = fixture();
	const tools = await setup(controller);
	for (const metric of ["median_ms", "mean_ms", "p95_ms"])
		envelope(await tools.get("set_metric").execute({ metric }), true);
	for (const metric of ["p99_ms", "__proto__", "", null, 1])
		envelope(await tools.get("set_metric").execute({ metric }), false);
	envelope(
		await tools.get("set_metric").execute({ metric: "median_ms", extra: true }),
		false,
	);
	assert.deepEqual(
		calls,
		["median_ms", "mean_ms", "p95_ms"].map((value) => ["metric", value]),
	);
});
check("controller failures become error envelopes", async () => {
	const { controller } = fixture();
	controller.getResults = () => {
		throw new Error("test failure");
	};
	envelope(
		await (await setup(controller)).get("get_results").execute({}),
		false,
	);
});
assert.equal(count, 8, "The independent WebMCP suite must contain eight tests");
