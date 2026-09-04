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

function activate(context) {
  const channel = vscode.window.createOutputChannel("MuxMender");
  context.subscriptions.push(channel);
  context.subscriptions.push(
    vscode.commands.registerCommand("muxmender.scanFolder", () =>
      chooseAndScan(channel)
    )
  );
  context.subscriptions.push(
    vscode.window.registerUriHandler({
      handleUri(uri) {
        if (uri.path !== "/scan") {
          return;
        }
        const folder = new URLSearchParams(uri.query).get("folder");
        if (!folder) {
          vscode.window.showErrorMessage("MuxMender scan URI is missing a folder.");
          return;
        }
        runDryScan(folder, channel);
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
