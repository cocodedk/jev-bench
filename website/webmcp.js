const METRICS = ["median_ms", "mean_ms", "p95_ms"];
const failure = (error) => ({ ok: false, error, data: null });
const success = (data) => ({ ok: true, error: null, data });

function validInput(input, keys) {
	return (
		input !== null &&
		typeof input === "object" &&
		!Array.isArray(input) &&
		Object.keys(input).length === keys.length &&
		keys.every((key) => Object.hasOwn(input, key))
	);
}

export async function registerPageTools(
	controller,
	registry = globalThis.document?.modelContext,
) {
	if (!registry || typeof registry.registerTool !== "function") return [];
	const definitions = [
		{
			name: "describe",
			description:
				"Describe the Jev Bench results page, its selected experiment, and available controls.",
			keys: [],
			readOnly: true,
			run: () => controller.describe(),
		},
		{
			name: "list_runs",
			description:
				"List the published classification experiments available in the page's experiment selector.",
			keys: [],
			readOnly: true,
			run: () => controller.listRuns(),
		},
		{
			name: "get_results",
			description:
				"Read the selected experiment's latency, accuracy, error counts, and returned model names.",
			keys: [],
			readOnly: true,
			run: () => controller.getResults(),
		},
		{
			name: "select_run",
			description:
				"Select a published experiment and return the results now displayed on the page.",
			keys: ["run_id"],
			readOnly: false,
			run: (input) => controller.selectRun(input.run_id),
		},
		{
			name: "set_metric",
			description:
				"Change the latency chart to median, mean, or p95 and return the updated displayed results.",
			keys: ["metric"],
			readOnly: false,
			run: (input) => controller.setMetric(input.metric),
		},
	];
	definitions.push(
		{
			name: "get_accuracy",
			description:
				"Read the selected model’s classification accuracy, per-class scores, and every incorrect prediction against the dataset labels.",
			keys: [],
			readOnly: true,
			run: () => controller.getAccuracy(),
		},
		{
			name: "select_accuracy_model",
			description:
				"Choose a model in the selected experiment and return the accuracy and mistakes now displayed on the page.",
			keys: ["model_name"],
			readOnly: false,
			run: (input) => controller.selectAccuracyModel(input.model_name),
		},
	);
	const registered = [];
	for (const definition of definitions) {
		const properties =
			definition.name === "select_accuracy_model"
				? { model_name: { type: "string" } }
				: definition.name === "select_run"
					? { run_id: { type: "string" } }
					: definition.name === "set_metric"
						? { metric: { type: "string", enum: METRICS } }
						: {};
		try {
			await registry.registerTool({
				name: definition.name,
				description: definition.description,
				inputSchema: {
					type: "object",
					properties,
					required: definition.keys,
					additionalProperties: false,
				},
				annotations: {
					readOnlyHint: definition.readOnly,
					consequentialHint: false,
					untrustedContentHint: [
						"get_results",
						"select_run",
						"set_metric",
						"get_accuracy",
						"select_accuracy_model",
					].includes(definition.name),
				},
				execute: async (input) => {
					if (!validInput(input, definition.keys))
						return failure("invalid_input");
					try {
						if (
							definition.name === "select_run" &&
							(typeof input.run_id !== "string" ||
								!controller.listRuns().some((run) => run.id === input.run_id))
						)
							return failure("unknown_run");
						if (
							definition.name === "set_metric" &&
							!METRICS.includes(input.metric)
						)
							return failure("unknown_metric");
						if (
							definition.name === "select_accuracy_model" &&
							(typeof input.model_name !== "string" ||
								!controller
									.getResults()
									.models.some((model) => model.name === input.model_name))
						)
							return failure("unknown_model");
						return success(await definition.run(input));
					} catch {
						return failure("unavailable");
					}
				},
			});
			registered.push(definition.name);
		} catch {
			/* One unavailable tool must not prevent the page or the other tools loading. */
		}
	}
	return registered;
}
