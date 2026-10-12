const failure = (error) => ({ ok: false, error, data: null });
const success = (data) => ({ ok: true, error: null, data });

export function testSetController(sets) {
	return {
		describe: () => ({
			title: "Jev Bench test sets",
			summary:
				"Every case of the decision benchmarks with its instructions, labels and expected answer.",
			sets: sets.map((set) => ({ id: set.name, type: set.type ?? "choice", cases: set.cases.length })),
		}),
		listTestSets: () =>
			sets.map((set) => ({ id: set.name, type: set.type ?? "choice", labels: set.labels, cases: set.cases.length })),
		getTestSet: (id) => sets.find((set) => set.name === id) ?? null,
	};
}

export async function registerTestSetTools(controller, registry = globalThis.document?.modelContext) {
	if (!registry || typeof registry.registerTool !== "function") return [];
	const definitions = [
		{ name: "describe", description: "Describe the test-sets page and the decision test sets it shows.", keys: [], run: () => controller.describe() },
		{ name: "list_test_sets", description: "List the published test sets with their question type, labels and case count.", keys: [], run: () => controller.listTestSets() },
		{ name: "get_test_set", description: "Read one test set's instructions, labels, criteria, cases and expected answers.", keys: ["set_id"], run: (input) => controller.getTestSet(input.set_id) },
	];
	const registered = [];
	for (const definition of definitions) {
		try {
			await registry.registerTool({
				name: definition.name,
				description: definition.description,
				inputSchema: {
					type: "object",
					properties: definition.keys.length ? { set_id: { type: "string" } } : {},
					required: definition.keys,
					additionalProperties: false,
				},
				annotations: { readOnlyHint: true, consequentialHint: false, untrustedContentHint: definition.name === "get_test_set" },
				execute: async (input) => {
					const valid =
						input !== null && typeof input === "object" && !Array.isArray(input) &&
						Object.keys(input).length === definition.keys.length &&
						definition.keys.every((key) => typeof input[key] === "string");
					if (!valid) return failure("invalid_input");
					const data = definition.run(input);
					return data === null ? failure("unknown_set") : success(data);
				},
			});
			registered.push(definition.name);
		} catch {
			/* One unavailable tool must not prevent the page or the other tools loading. */
		}
	}
	return registered;
}

const embedded = globalThis.document?.getElementById("test-sets");
if (embedded) registerTestSetTools(testSetController(JSON.parse(embedded.textContent)));
