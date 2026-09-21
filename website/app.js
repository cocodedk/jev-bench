import { registerPageTools } from "./webmcp.js";

const METRICS = { median_ms: "Median", mean_ms: "Mean", p95_ms: "p95" };
const byId = (id) => document.getElementById(id);
const format = (value) => (Number.isFinite(value) ? value.toFixed(1) : "—");
let runs = [];
let selected = null;
let metric = "median_ms";

function element(tag, className, text) {
	const node = document.createElement(tag);
	if (className) node.className = className;
	if (text !== undefined) node.textContent = text;
	return node;
}

function snapshot() {
	return {
		run_id: selected.id,
		title: selected.title,
		metric,
		started_utc: selected.started_utc,
		measured_calls: selected.measured_calls,
		dataset: selected.dataset,
		notes: selected.notes,
		models: selected.models.map((model) => ({
			name: model.name,
			returned_models: [...model.returned_models],
			median_ms: model.median_ms,
			mean_ms: model.mean_ms,
			p95_ms: model.p95_ms,
			valid_responses: model.valid_responses,
			planned: model.planned,
			correct_labels: model.correct_labels,
			errors: model.errors,
			skipped: model.skipped,
		})),
		downloads: { json: selected.json_url, csv: selected.csv_url },
	};
}

function render() {
	const models = selected.models;
	byId("run-picker").value = selected.id;
	byId("calls").textContent = String(selected.measured_calls);
	byId("models").textContent = String(models.length);
	byId("correct").textContent =
		`${models.reduce((sum, m) => sum + m.correct_labels, 0)} / ${models.reduce((sum, m) => sum + m.valid_responses, 0)}`;
	byId("run-date").textContent = new Date(
		selected.started_utc,
	).toLocaleDateString("en-GB", {
		day: "2-digit",
		month: "short",
		year: "numeric",
		timeZone: "UTC",
	});
	byId("run-title").textContent = selected.title;
	byId("run-subtitle").textContent = selected.subtitle;
	byId("dataset").textContent = selected.dataset;
	byId("sample").textContent =
		`${selected.cases} cases × ${selected.rounds} round${selected.rounds === 1 ? "" : "s"}`;
	byId("errors").textContent = String(
		models.reduce((sum, m) => sum + m.errors, 0),
	);
	byId("run-notes").textContent = selected.notes;
	byId("json-link").href = selected.json_url;
	byId("csv-link").href = selected.csv_url;
	byId("metric-description").textContent =
		`${METRICS[metric]} request latency · lower is faster`;
	document
		.querySelectorAll("[data-metric]")
		.forEach((button) =>
			button.setAttribute(
				"aria-pressed",
				String(button.dataset.metric === metric),
			),
		);
	const chart = byId("chart");
	chart.replaceChildren();
	const max = Math.max(1, ...models.map((model) => model[metric] ?? 0)) * 1.08;
	for (const model of models) {
		const row = element("div", "bar-row");
		const top = element("div", "bar-top");
		top.append(element("span", "bar-label", model.label));
		const value = element("span", "bar-value", format(model[metric]));
		value.append(element("small", "", " ms"));
		top.append(value);
		const track = element("div", "bar-track");
		const fill = element("div", "bar-fill");
		fill.style.width = `${Number.isFinite(model[metric]) ? (model[metric] / max) * 100 : 0}%`;
		track.append(fill);
		row.append(top, track);
		chart.append(row);
	}
	const tbody = byId("results-body");
	tbody.replaceChildren();
	for (const model of models) {
		const tr = element("tr");
		const name = element("td", "", model.label);
		name.append(
			element(
				"small",
				"",
				model.returned_models.join(", ") || "Model not reported",
			),
		);
		tr.append(name);
		for (const key of ["median_ms", "mean_ms", "p95_ms"])
			tr.append(element("td", "", `${format(model[key])} ms`));
		tr.append(
			element("td", "", `${model.correct_labels}/${model.valid_responses}`),
		);
		tr.append(element("td", "", String(model.errors)));
		tbody.append(tr);
	}
	byId("load-status").textContent =
		`${selected.complete ? "Complete" : "Incomplete"} run · ${selected.attempts_used} total attempts including warmups`;
}

const controller = {
	describe: () => ({
		page: "Jev Bench classifier workbench",
		content: "Published API classification latency and correctness experiments",
		selected_run: selected.id,
		metric,
		controls: ["experiment selector", "latency metric buttons"],
		available_metrics: Object.keys(METRICS),
		available_run_ids: runs.map((run) => run.id),
	}),
	listRuns: () => runs.map((run) => ({ id: run.id, title: run.title })),
	getResults: snapshot,
	selectRun: (id) => {
		const run = runs.find((item) => item.id === id);
		if (run) {
			selected = run;
			render();
		}
		return snapshot();
	},
	setMetric: (value) => {
		if (Object.hasOwn(METRICS, value)) {
			metric = value;
			render();
		}
		return snapshot();
	},
};

async function init() {
	try {
		const response = await fetch("data/runs.json");
		if (!response.ok) throw new Error("Results unavailable");
		const data = await response.json();
		if (!Array.isArray(data.runs) || data.runs.length === 0)
			throw new Error("No published runs");
		runs = data.runs;
		selected = runs[0];
		const picker = byId("run-picker");
		picker.replaceChildren();
		for (const run of runs) {
			const option = element("option", "", run.title);
			option.value = run.id;
			picker.append(option);
		}
		picker.addEventListener("change", () => controller.selectRun(picker.value));
		document
			.querySelectorAll("[data-metric]")
			.forEach((button) =>
				button.addEventListener("click", () =>
					controller.setMetric(button.dataset.metric),
				),
			);
		render();
		await registerPageTools(controller);
	} catch {
		byId("load-status").textContent =
			"Published results could not load; the complete data is available in the GitHub repository.";
	}
}

void init();
