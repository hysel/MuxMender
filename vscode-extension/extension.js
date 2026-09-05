"use strict";

const fs = require("fs");
const path = require("path");
const { spawn } = require("child_process");
const vscode = require("vscode");
const { createProgressParser } = require("./progress");
const { decodeMediaPath } = require("./media-path");

let activeProcess;

function findScript() {
  const configured = vscode.workspace
    .getConfiguration("muxmender")
    .get("scriptPath", "")
    .trim();
  if (configured) {
    return configured.replace(
      "${workspaceFolder}",
      vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || "",
    );
  }

  for (const folder of vscode.workspace.workspaceFolders || []) {
    const candidate = path.join(folder.uri.fsPath, "muxmender.py");
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }
  return undefined;
}

function reportPath(scriptPath) {
  const reportDirectory = path.join(path.dirname(scriptPath), "reports");
  fs.mkdirSync(reportDirectory, { recursive: true });
  return path.join(reportDirectory, "vscode-scan.json");
}

function configuredHardware() {
  return vscode.workspace
    .getConfiguration("muxmender")
    .get("hardware", "auto");
}

function configuredResolution() {
  return vscode.workspace
    .getConfiguration("muxmender")
    .get("resolution", "keep");
}

function configuredDolbyVisionPolicy() {
  return vscode.workspace
    .getConfiguration("muxmender")
    .get("dolbyVisionPolicy", "skip");
}

function configuredFfmpeg() {
  return vscode.workspace.getConfiguration("muxmender").get("ffmpegPath", "ffmpeg");
}

function configuredFfprobe() {
  return vscode.workspace.getConfiguration("muxmender").get("ffprobePath", "ffprobe");
}

function actionFromOutput(output, marker) {
  const prefix = `${marker}=`;
  const line = output.split(/\r?\n/).findLast((item) => item.startsWith(prefix));
  if (!line) {
    return undefined;
  }
  try {
    return JSON.parse(line.slice(prefix.length));
  } catch {
    return undefined;
  }
}

async function offerRecovery(file, channel, output) {
  const requirement = actionFromOutput(output, "MUXMENDER_REQUIREMENT");
  const failure = actionFromOutput(output, "MUXMENDER_HARDWARE_FAILURE");
  const colorFailure = actionFromOutput(output, "MUXMENDER_COLOR_PIPELINE_FAILURE");
  const action = requirement || failure || colorFailure;
  if (!action) {
    return;
  }

  const choices = ["Download / Install"];
  if (failure || requirement?.cpu_available || colorFailure?.cpu_available) {
    choices.unshift("Use CPU");
  }
  const selected = await vscode.window.showWarningMessage(
    action.message || "MuxMender hardware encoding is unavailable.",
    ...choices,
  );
  if (selected === "Use CPU") {
    channel.appendLine("\nUser selected CPU fallback.\n");
    return runSafeCopy(file, channel, "cpu");
  }
  if (selected === "Download / Install" && action.download_url) {
    await vscode.env.openExternal(vscode.Uri.parse(action.download_url));
    vscode.window.showInformationMessage(
      "Complete the official installer, restart VS Code if requested, then run MuxMender again."
    );
  }
}

function runDryScan(folder, channel) {
  if (activeProcess) {
    vscode.window.showWarningMessage("A MuxMender scan is already running.");
    channel.show(true);
    return;
  }

  const script = findScript();
  if (!script || !fs.existsSync(script)) {
    vscode.window.showErrorMessage(
      "MuxMender could not find muxmender.py in the open workspace."
    );
    return;
  }
  if (!fs.existsSync(folder)) {
    vscode.window.showErrorMessage(`Media folder does not exist: ${folder}`);
    return;
  }

  const python = vscode.workspace
    .getConfiguration("muxmender")
    .get("pythonPath", "python");
  const report = reportPath(script);

  channel.clear();
  channel.appendLine("MuxMender VS Code scan");
  channel.appendLine(`Folder: ${folder}`);
  channel.appendLine("Mode: DRY RUN (read-only; no conversion or deletion)\n");
  channel.show(true);

  const child = spawn(
    python,
    [
      script, folder, "--dry-run", "--hardware", configuredHardware(),
      "--resolution", configuredResolution(), "--hardware-fallback", "never",
      "--dolby-vision-policy", configuredDolbyVisionPolicy(),
      "--ffmpeg", configuredFfmpeg(), "--ffprobe", configuredFfprobe(),
      "--report", report,
    ],
    {
      cwd: path.dirname(script),
      windowsHide: true,
      shell: false,
      env: { ...process.env, PYTHONIOENCODING: "utf-8" },
    }
  );
  activeProcess = child;
  child.stdout.setEncoding("utf8");
  child.stderr.setEncoding("utf8");
  child.stdout.on("data", (data) => channel.append(data));
  child.stderr.on("data", (data) => channel.append(data));
  child.on("error", (error) => {
    channel.appendLine(`\nFailed to start scan: ${error.message}`);
    activeProcess = undefined;
  });
  child.on("close", (code) => {
    channel.appendLine(
      `\nScan ${code === 0 ? "completed successfully" : `failed with exit code ${code}`}.`
    );
    channel.appendLine(`JSON report: ${report}`);
    activeProcess = undefined;
  });
}

function runSafeCopy(file, channel, hardwareOverride) {
  if (activeProcess) {
    vscode.window.showWarningMessage("A MuxMender operation is already running.");
    channel.show(true);
    return;
  }

  const script = findScript();
  if (!script || !fs.existsSync(script)) {
    vscode.window.showErrorMessage(
      "MuxMender could not find muxmender.py in the open workspace."
    );
    return;
  }
  if (!fs.existsSync(file) || !fs.statSync(file).isFile()) {
    vscode.window.showErrorMessage(`Media file does not exist: ${file}`);
    return;
  }

  const python = vscode.workspace
    .getConfiguration("muxmender")
    .get("pythonPath", "python");
  const outputDirectory = path.join(path.dirname(script), "test-output");
  const reportDirectory = path.join(path.dirname(script), "reports");
  fs.mkdirSync(outputDirectory, { recursive: true });
  fs.mkdirSync(reportDirectory, { recursive: true });
  const report = path.join(reportDirectory, "vscode-optimize.json");
  const hardware = hardwareOverride || configuredHardware();
  const resolution = configuredResolution();
  const dolbyVisionPolicy = configuredDolbyVisionPolicy();

  channel.clear();
  channel.appendLine("MuxMender safe single-file optimization");
  channel.appendLine(`Source: ${file}`);
  channel.appendLine(`Output directory: ${outputDirectory}`);
  channel.appendLine(`Hardware preference: ${hardware} (GPU-first when auto)`);
  channel.appendLine(`Resolution policy: ${resolution} (upscaling disabled)`);
  channel.appendLine(`Dolby Vision policy: ${dolbyVisionPolicy} (re-encoding blocked)`);
  channel.appendLine("Original protection: ON (the source cannot be deleted or overwritten)\n");
  channel.show(true);

  return vscode.window.withProgress(
    {
      location: vscode.ProgressLocation.Notification,
      title: `MuxMender: ${path.basename(file)}`,
      cancellable: false,
    },
    (progress) =>
      new Promise((resolve) => {
        const child = spawn(
          python,
          [
            script,
            file,
            "--execute",
            "--hardware",
            hardware,
            "--hardware-fallback",
            "never",
            "--resolution",
            resolution,
            "--dolby-vision-policy",
            dolbyVisionPolicy,
            "--ffmpeg",
            configuredFfmpeg(),
            "--ffprobe",
            configuredFfprobe(),
            "--output-dir",
            outputDirectory,
            "--report",
            report,
          ],
          {
            cwd: path.dirname(script),
            windowsHide: true,
            shell: false,
            env: { ...process.env, PYTHONIOENCODING: "utf-8" },
          }
        );
        activeProcess = child;
        let lastPercent = 0;
        let processOutput = "";
        child.stdout.setEncoding("utf8");
        child.stderr.setEncoding("utf8");
        child.stdout.on("data", (data) => {
          processOutput += data;
          channel.append(data);
          for (const match of data.matchAll(/MUXMENDER_PROGRESS=(\d+(?:\.\d+)?)/g)) {
            const percent = Math.min(100, Number(match[1]));
            progress.report({
              increment: Math.max(0, percent - lastPercent),
              message: `${percent.toFixed(1)}%`,
            });
            lastPercent = Math.max(lastPercent, percent);
          }
        });
        child.stderr.on("data", (data) => {
          processOutput += data;
          channel.append(data);
        });
        child.on("error", (error) => {
          channel.appendLine(`\nFailed to start optimization: ${error.message}`);
          activeProcess = undefined;
          resolve();
        });
        child.on("close", (code) => {
          channel.appendLine(
            `\nOptimization ${code === 0 ? "completed successfully" : `failed with exit code ${code}`}.`
          );
          channel.appendLine(`JSON report: ${report}`);
          activeProcess = undefined;
          resolve();
          setTimeout(() => offerRecovery(file, channel, processOutput), 0);
        });
      })
  );
}

async function chooseAndScan(channel) {
  const selected = await vscode.window.showOpenDialog({
    canSelectFiles: false,
    canSelectFolders: true,
    canSelectMany: false,
    openLabel: "Scan folder (dry run)",
    title: "Choose a media folder for MuxMender",
  });
  if (selected?.[0]) {
    runDryScan(selected[0].fsPath, channel);
  }
}

async function chooseAndOptimize(channel) {
  const selected = await vscode.window.showOpenDialog({
    canSelectFiles: true,
    canSelectFolders: false,
    canSelectMany: false,
    openLabel: "Optimize safe copy",
    title: "Choose one media file for MuxMender",
    filters: {
      "Media files": [
        "3gp", "avi", "flv", "m2ts", "m4v", "mkv", "mov", "mp4",
        "mpeg", "mpg", "mts", "ts", "webm", "wmv"
      ],
    },
  });
  if (selected?.[0]) {
    return runSafeCopy(selected[0].fsPath, channel);
  }
}

function activate(context) {
  const channel = vscode.window.createOutputChannel("MuxMender");
  context.subscriptions.push(channel);
  context.subscriptions.push(vscode.commands.registerCommand("muxmender.deliveryTest", async () => {
    const selected = await vscode.window.showOpenDialog({ canSelectFiles: true, canSelectFolders: false, canSelectMany: false, title: "Select Dolby Vision profile 5 source for a safe 10-second HDR test" });
    if (selected?.[0]) return runDeliveryTest(selected[0].fsPath, channel, configuredHardware());
  }));
  context.subscriptions.push(vscode.commands.registerCommand("muxmender.previewFile", async () => {
    const selected = await vscode.window.showOpenDialog({ canSelectFiles: true, canSelectFolders: false, canSelectMany: false, title: "Select Dolby Vision profile 5 source (original stays untouched)" });
    if (!selected?.[0]) return;
    const mode = await vscode.window.showQuickPick(["HDR PQ (drops Dolby Vision metadata)", "SDR BT.709"], { title: "Choose diagnostic output color" });
    if (mode) return runNativePreview(selected[0].fsPath, channel, mode.startsWith("HDR") ? "hdr-preview" : "sdr-preview");
  }));
  context.subscriptions.push(
    vscode.commands.registerCommand("muxmender.scanFolder", () =>
      chooseAndScan(channel)
    )
  );
  context.subscriptions.push(
    vscode.commands.registerCommand("muxmender.optimizeFile", () =>
      chooseAndOptimize(channel)
    )
  );
  context.subscriptions.push(
    vscode.commands.registerCommand("muxmender.optimizePath", (file, hardware) =>
      runSafeCopy(file, channel, hardware)
    )
  );
  context.subscriptions.push(
    vscode.window.registerUriHandler({
      handleUri(uri) {
        const parameters = new URLSearchParams(uri.query);
        let mediaFile;
        try { if (uri.path !== "/scan") mediaFile = decodeMediaPath(parameters, "file"); }
        catch (error) { return vscode.window.showErrorMessage(`Invalid MuxMender path: ${error.message}`); }
        if (uri.path === "/delivery") {
          return runDeliveryTest(mediaFile, channel, parameters.get("hardware") || "auto");
        }
        if (uri.path === "/preview") {
          const file = mediaFile;
          if (file) return runNativePreview(file, channel, parameters.get("mode") === "sdr-preview" ? "sdr-preview" : "hdr-preview");
          return;
        }
        if (uri.path === "/scan") {
          const folder = parameters.get("folder");
          if (!folder) {
            vscode.window.showErrorMessage("MuxMender scan URI is missing a folder.");
            return;
          }
          return runDryScan(folder, channel);
        }
        if (uri.path === "/optimize") {
          const file = mediaFile;
          if (!file) {
            vscode.window.showErrorMessage("MuxMender optimize URI is missing a file.");
            return;
          }
          return runSafeCopy(file, channel);
        }
      },
    })
  );

}

function deactivate() {
  if (activeProcess) {
    activeProcess.kill();
    activeProcess = undefined;
  }
}

module.exports = { activate, deactivate };

async function runNativePreview(file, channel, mode) {
  if (activeProcess) return vscode.window.showWarningMessage("MuxMender is already running.");
  const script = findScript();
  if (!script || !fs.existsSync(script) || !fs.existsSync(file))
    return vscode.window.showErrorMessage("MuxMender script or source file is missing.");
  const helper = path.join(path.dirname(script), "native", "muxmender-d3d11", "build", "preview", "muxmender-dv-preview.exe");
  if (!fs.existsSync(helper)) return vscode.window.showErrorMessage("The native helper has not been built. See native/muxmender-d3d11/README.md. No media was changed.");
  const output = path.join(path.dirname(script), "test-output", `native-${Date.now()}`);
  const python = vscode.workspace.getConfiguration("muxmender").get("pythonPath", "python");
  channel.clear(); channel.show(true);
  channel.appendLine(`Native ${mode}: 3-second diagnostic at 00:05:00. Original dimensions, video only.`);
  channel.appendLine(`Source: ${file}\nOutput: ${output}\nOriginal protection: ON. No deletion or overwrite.\n`);
  return vscode.window.withProgress({ location: vscode.ProgressLocation.Notification, title: "MuxMender: native color preview", cancellable: false }, progress => new Promise(resolve => {
    const parseProgress = createProgressParser(update => progress.report(update));
    const child = spawn(python, [script, file, "--execute", "--dolby-vision-policy", mode, "--dolby-preview-backend", "d3d11", "--preview-seconds", "3", "--output-dir", output, "--ffprobe", configuredFfprobe()], {
      cwd: path.dirname(script), windowsHide: true, shell: false, env: { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONUNBUFFERED: "1" },
    });
    activeProcess = child;
    child.stdout.setEncoding("utf8"); child.stderr.setEncoding("utf8");
    child.stdout.on("data", data => { channel.append(data); parseProgress(data); });
    child.stderr.on("data", data => channel.append(data));
    child.on("error", error => { channel.appendLine(`Failed to start: ${error.message}`); activeProcess = undefined; resolve(); });
    child.on("close", code => {
      channel.appendLine(`\nNative preview ${code === 0 ? "completed and verified" : `failed (${code}); partial outputs retained`}. Originals untouched.`);
      activeProcess = undefined; resolve();
    });
  }));
}

async function runDeliveryTest(file, channel, hardware = "auto") {
  if (activeProcess) return vscode.window.showWarningMessage("MuxMender is already running.");
  if (!["auto", "amd", "nvidia", "intel", "cpu"].includes(hardware)) return vscode.window.showErrorMessage("Invalid hardware selection.");
  const script = findScript();
  if (!script || !fs.existsSync(script)) return vscode.window.showErrorMessage("MuxMender script was not found. Check muxmender.scriptPath.");
  if (!file || !fs.existsSync(file)) return vscode.window.showErrorMessage(`MuxMender source is not accessible: ${file || "missing path"}`);
  const config = vscode.workspace.getConfiguration("muxmender");
  const args = [script, file, "--execute", "--native-delivery-test", "--dolby-vision-policy", "hdr-preview",
    "--dolby-preview-backend", "d3d11", "--preview-seconds", "10", "--hardware", hardware,
    "--hardware-fallback", "never", "--resolution", "keep", "--ffmpeg", configuredFfmpeg(), "--ffprobe", configuredFfprobe(),
    "--output-dir", path.join(path.dirname(script), "test-output")];
  const runtime = config.get("nativeHelperPath", "").trim();
  if (runtime) args.push("--d3d11-helper", runtime);
  channel.clear(); channel.show(true);
  channel.appendLine(`10-second HDR delivery test: ${hardware}.\nSource: ${file}\nOriginal protection: ON. Exact dimensions, audio/subtitles copied.\nOutput is HDR PQ, not Dolby Vision.\n`);
  let processOutput = "";
  const result = await vscode.window.withProgress({ location: vscode.ProgressLocation.Notification, title: "MuxMender: HDR delivery test", cancellable: false }, progress => new Promise(resolve => {
    const parseProgress = createProgressParser(update => progress.report(update));
    const child = spawn(config.get("pythonPath", "python"), args, { cwd: path.dirname(script), windowsHide: true, shell: false,
      env: { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONUNBUFFERED: "1" } });
    activeProcess = child;
    child.stdout.setEncoding("utf8"); child.stderr.setEncoding("utf8");
    const receive = data => { channel.append(data); parseProgress(data); processOutput += data; };
    child.stdout.on("data", receive); child.stderr.on("data", receive);
    child.on("error", error => { channel.appendLine(`Failed to start: ${error.message}`); activeProcess = undefined; resolve(-1); });
    child.on("close", code => { activeProcess = undefined; channel.appendLine(`\nHDR test ${code === 0 ? "completed" : `failed (${code})`}. Originals untouched; outputs retained.`); resolve(code); });
  }));
  if (result === 0) return;
  const action = actionFromOutput(processOutput, "MUXMENDER_REQUIREMENT") || actionFromOutput(processOutput, "MUXMENDER_HARDWARE_FAILURE");
  if (!action) return;
  const choices = [];
  if (action.cpu_available && hardware !== "cpu") choices.push("Retry with CPU");
  if (action.download_url) choices.push("Open official download");
  const selected = await vscode.window.showWarningMessage(action.message, ...choices);
  if (selected === "Retry with CPU") return runDeliveryTest(file, channel, "cpu");
  if (selected === "Open official download") return vscode.env.openExternal(vscode.Uri.parse(action.download_url));
}
