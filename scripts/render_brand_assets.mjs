// Render the editable SVG artwork with Chrome; no image-generation or runtime dependencies.
import { spawn } from "node:child_process";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const profile = await mkdtemp(resolve(tmpdir(), "jev-brand-"));
const delay = (ms) => new Promise((done) => setTimeout(done, ms));
const chrome = spawn(
	process.env.CHROME || "/usr/bin/google-chrome",
	[
		"--headless=new",
		"--no-sandbox",
		"--disable-dev-shm-usage",
		"--remote-debugging-port=0",
		`--user-data-dir=${profile}`,
		"about:blank",
	],
	{ stdio: "ignore" },
);
let socket;
try {
	let target;
	for (let index = 0; index < 100; index++) {
		try {
			const [port] = (
				await readFile(resolve(profile, "DevToolsActivePort"), "utf8")
			).split("\n");
			const targets = await (
				await fetch(`http://127.0.0.1:${port}/json/list`)
			).json();
			target = targets.find((item) => item.type === "page");
			if (target) break;
		} catch {
			/* Wait for Chrome to open its temporary debugging port. */
		}
		if (chrome.exitCode !== null)
			throw new Error("Chrome exited before rendering");
		await delay(50);
	}
	if (!target) throw new Error("Chrome did not start within five seconds");
	socket = new WebSocket(target.webSocketDebuggerUrl);
	await new Promise((done, reject) => {
		socket.addEventListener("open", done, { once: true });
		socket.addEventListener("error", reject, { once: true });
	});
	let sequence = 0;
	async function render(source, width, height) {
		const svg = await readFile(resolve(root, source), "utf8");
		const url = `data:image/svg+xml;base64,${Buffer.from(svg).toString("base64")}`;
		const expression = `(async () => {
      const image = new Image(); image.src = ${JSON.stringify(url)}; await image.decode();
      const canvas = document.createElement('canvas'); canvas.width = ${width}; canvas.height = ${height};
      canvas.getContext('2d').drawImage(image, 0, 0, ${width}, ${height}); return canvas.toDataURL('image/png');
    })()`;
		const id = ++sequence;
		const response = await new Promise((done, reject) => {
			const timer = setTimeout(() => {
				socket.removeEventListener("message", receive);
				reject(new Error("Render timed out"));
			}, 10000);
			function receive(event) {
				const message = JSON.parse(event.data);
				if (message.id !== id) return;
				clearTimeout(timer);
				socket.removeEventListener("message", receive);
				if (message.error || message.result.exceptionDetails)
					reject(
						new Error(
							JSON.stringify(message.error || message.result.exceptionDetails),
						),
					);
				else done(message.result.result.value);
			}
			socket.addEventListener("message", receive);
			socket.send(
				JSON.stringify({
					id,
					method: "Runtime.evaluate",
					params: { expression, awaitPromise: true, returnByValue: true },
				}),
			);
		});
		return Buffer.from(response.split(",")[1], "base64");
	}
	for (const [source, name, width, height] of [
		["assets/og-image.svg", "og-image.png", 1200, 630],
		["website/favicon.svg", "favicon-96.png", 96, 96],
		["website/favicon.svg", "apple-touch-icon.png", 180, 180],
	]) {
		const content = await render(source, width, height);
		await writeFile(resolve(root, "website", name), content);
		console.log(`${name}: ${width}×${height}, ${content.length} bytes`);
	}
	const sizes = [16, 32, 48];
	const images = [];
	for (const size of sizes)
		images.push(await render("website/favicon.svg", size, size));
	const header = Buffer.alloc(6 + 16 * sizes.length);
	header.writeUInt16LE(1, 2);
	header.writeUInt16LE(sizes.length, 4);
	let offset = header.length;
	sizes.forEach((size, index) => {
		const entry = 6 + 16 * index;
		header[entry] = size;
		header[entry + 1] = size;
		header.writeUInt16LE(1, entry + 4);
		header.writeUInt16LE(32, entry + 6);
		header.writeUInt32LE(images[index].length, entry + 8);
		header.writeUInt32LE(offset, entry + 12);
		offset += images[index].length;
	});
	await writeFile(
		resolve(root, "website/favicon.ico"),
		Buffer.concat([header, ...images]),
	);
	console.log("favicon.ico: 16×16, 32×32, 48×48");
} finally {
	socket?.close();
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
