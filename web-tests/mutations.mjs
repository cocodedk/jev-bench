import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtemp, mkdir, readFile, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const source = await readFile(resolve(root, "website/webmcp.js"), "utf8");
const tests = await readFile(
	resolve(root, "web-tests/webmcp.test.mjs"),
	"utf8",
);
const mutations = [
	["closed input keys", "Object.keys(input).length === keys.length", "true"],
	["metric allowlist", "!METRICS.includes(input.metric)", "false"],
	[
		"run allowlist",
		"!controller.listRuns().some((run) => run.id === input.run_id)",
		"false",
	],
	[
		"read-only annotation",
		"readOnlyHint: definition.readOnly",
		"readOnlyHint: true",
	],
];
assert.equal(mutations.length, 4);
const directory = await mkdtemp(resolve(tmpdir(), "jev-webmcp-mutations-"));
const killed = [];
try {
	await mkdir(resolve(directory, "website"));
	await mkdir(resolve(directory, "web-tests"));
	await writeFile(resolve(directory, "package.json"), '{"type":"module"}\n');
	await writeFile(resolve(directory, "web-tests/webmcp.test.mjs"), tests);
	await writeFile(resolve(directory, "website/webmcp.js"), source);
	const baseline = spawnSync(
		process.execPath,
		["--test", "web-tests/webmcp.test.mjs"],
		{ cwd: directory, encoding: "utf8" },
	);
	assert.equal(
		baseline.status,
		0,
		`Unmutated tests must pass first:\n${baseline.stdout}${baseline.stderr}`,
	);
	assert.match(baseline.stdout, /tests 8/);
	for (const [name, before, after] of mutations) {
		assert.equal(
			source.split(before).length,
			2,
			`Mutation must change exactly one site: ${name}`,
		);
		await writeFile(
			resolve(directory, "website/webmcp.js"),
			source.replace(before, after),
		);
		const result = spawnSync(
			process.execPath,
			["--test", "web-tests/webmcp.test.mjs"],
			{ cwd: directory, encoding: "utf8" },
		);
		assert.equal(
			result.status,
			1,
			`Tests must kill mutation: ${name}\n${result.stdout}${result.stderr}`,
		);
		assert.match(
			result.stdout,
			/tests 8/,
			`Mutation must run all eight tests: ${name}`,
		);
		killed.push(name);
	}
} finally {
	await rm(directory, { recursive: true, force: true });
}
assert.equal(killed.length, 4);
console.log(
	JSON.stringify({ mutants: 4, killed: killed.length, checks: killed }),
);
