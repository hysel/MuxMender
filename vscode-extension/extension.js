"use strict";

const fs = require("fs");
const path = require("path");
const { spawn } = require("child_process");
const vscode = require("vscode");

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
    [script, folder, "--dry-run", "--report", report],
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

function runSafeCopy(file, channel) {
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

  channel.clear();
  channel.appendLine("MuxMender safe single-file optimization");
  channel.appendLine(`Source: ${file}`);
  channel.appendLine(`Output directory: ${outputDirectory}`);
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
        child.stdout.setEncoding("utf8");
        child.stderr.setEncoding("utf8");
        child.stdout.on("data", (data) => {
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
        child.stderr.on("data", (data) => channel.append(data));
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
    vscode.window.registerUriHandler({
      handleUri(uri) {
        const parameters = new URLSearchParams(uri.query);
        if (uri.path === "/scan") {
          const folder = parameters.get("folder");
          if (!folder) {
            vscode.window.showErrorMessage("MuxMender scan URI is missing a folder.");
            return;
          }
          return runDryScan(folder, channel);
        }
        if (uri.path === "/optimize") {
          const file = parameters.get("file");
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
