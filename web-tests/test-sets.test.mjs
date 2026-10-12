import assert from "node:assert/strict";
import { test } from "node:test";
import { registerTestSetTools, testSetController } from "../website/test-sets.js";

const sets = [{ name: "decisions-noul", type: "noul", instructions: "i", labels: ["true", "false"], cases: [{ id: "n-01", text: "t", expected: "true" }] }];

async function tools() {
	const registered = {};
	const names = await registerTestSetTools(testSetController(sets), { registerTool: (tool) => { registered[tool.name] = tool; } });
	return { names, registered };
}

test("registers three read-only tools with closed inputs", async () => {
	const { names, registered } = await tools();
	assert.deepEqual(names, ["describe", "list_test_sets", "get_test_set"]);
	for (const tool of Object.values(registered)) {
		assert.equal(tool.annotations.readOnlyHint, true);
		assert.equal(tool.inputSchema.additionalProperties, false);
		assert.equal(tool.annotations.untrustedContentHint, tool.name === "get_test_set");
	}
});

test("answers describe, list and get with the {ok, error, data} shape", async () => {
	const { registered } = await tools();
	assert.deepEqual((await registered.describe.execute({})).data.sets, [{ id: "decisions-noul", type: "noul", cases: 1 }]);
	assert.equal((await registered.list_test_sets.execute({})).data[0].labels.length, 2);
	assert.deepEqual(await registered.get_test_set.execute({ set_id: "decisions-noul" }), { ok: true, error: null, data: sets[0] });
});

test("refuses unknown sets and malformed input", async () => {
	const { registered } = await tools();
	assert.deepEqual(await registered.get_test_set.execute({ set_id: "nope" }), { ok: false, error: "unknown_set", data: null });
	for (const input of [{}, { set_id: 1 }, { set_id: "decisions-noul", extra: 1 }, null, []])
		assert.equal((await registered.get_test_set.execute(input)).error, "invalid_input");
	assert.equal((await registered.describe.execute({ x: 1 })).error, "invalid_input");
});

test("no registry, no tools", async () => {
	assert.deepEqual(await registerTestSetTools(testSetController(sets), undefined), []);
});
