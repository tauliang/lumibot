"""Flask app for the Local Backtest Studio."""

from __future__ import annotations

import socket
import webbrowser
from pathlib import Path

from flask import Flask, jsonify, request, send_file

from .artifacts import read_table, resolve_artifact_path
from .manager import RunManager
from .models import StudioValidationError, discover_strategy_classes, resolve_user_path, static_strategy_warnings
from .templates import list_templates


def create_app(workspace: str | Path | None = None, runs_dir: str | Path | None = None) -> Flask:
    workspace_path = Path(workspace or Path.cwd()).resolve()
    runs_path = Path(runs_dir).resolve() if runs_dir else workspace_path / ".lumibot" / "studio" / "runs"
    manager = RunManager(workspace_path, runs_path)

    app = Flask(__name__)
    app.config["studio_manager"] = manager

    @app.get("/")
    def index():
        return INDEX_HTML

    @app.get("/api/health")
    def health():
        return jsonify(
            {
                "ok": True,
                "workspace": str(manager.workspace),
                "runs_dir": str(manager.runs_dir),
            }
        )

    @app.get("/api/templates")
    def templates():
        return jsonify({"templates": list_templates()})

    @app.post("/api/strategies/discover")
    def discover_strategy():
        payload = request.get_json(silent=True) or {}
        try:
            path = resolve_user_path(payload.get("path") or "", manager.workspace)
            return jsonify(
                {
                    "path": str(path),
                    "classes": discover_strategy_classes(path),
                    "warnings": static_strategy_warnings(path),
                }
            )
        except Exception as exc:
            return jsonify({"error": str(exc)}), 400

    @app.post("/api/preflight")
    def preflight():
        payload = request.get_json(silent=True) or {}
        try:
            return jsonify(manager.preflight(payload))
        except (StudioValidationError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400

    @app.post("/api/runs")
    def create_run():
        payload = request.get_json(silent=True) or {}
        try:
            return jsonify(manager.submit(payload)), 201
        except (StudioValidationError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400

    @app.get("/api/runs")
    def list_runs():
        return jsonify({"runs": manager.list_runs()})

    @app.get("/api/runs/<run_id>")
    def get_run(run_id):
        try:
            return jsonify(manager.get_run(run_id))
        except FileNotFoundError:
            return jsonify({"error": "run not found"}), 404

    @app.post("/api/runs/<run_id>/cancel")
    def cancel_run(run_id):
        try:
            return jsonify(manager.cancel(run_id))
        except FileNotFoundError:
            return jsonify({"error": "run not found"}), 404

    @app.get("/api/runs/<run_id>/logs")
    def get_logs(run_id):
        return jsonify(manager.get_logs(run_id, offset=int(request.args.get("offset", 0))))

    @app.get("/api/runs/<run_id>/artifacts")
    def get_artifacts(run_id):
        try:
            return jsonify({"artifacts": manager.get_run(run_id)["status"]["artifacts"]})
        except FileNotFoundError:
            return jsonify({"error": "run not found"}), 404

    @app.get("/api/runs/<run_id>/artifacts/<path:artifact_name>")
    def get_artifact(run_id, artifact_name):
        try:
            path = resolve_artifact_path(manager.run_dir(run_id), artifact_name)
            return send_file(path, as_attachment=False)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except FileNotFoundError:
            return jsonify({"error": "artifact not found"}), 404

    @app.get("/api/runs/<run_id>/table/<path:artifact_name>")
    def get_table(run_id, artifact_name):
        try:
            return jsonify(
                read_table(
                    manager.run_dir(run_id),
                    artifact_name,
                    offset=int(request.args.get("offset", 0)),
                    limit=int(request.args.get("limit", 100)),
                )
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except FileNotFoundError:
            return jsonify({"error": "artifact not found"}), 404

    @app.get("/api/runs/<run_id>/chart-data")
    def get_chart_data(run_id):
        return jsonify(manager.chart_data(run_id))

    return app


def run_studio(host: str = "127.0.0.1", port: int = 8765, workspace: str | None = None, runs_dir: str | None = None, open_browser: bool = True) -> None:
    app = create_app(workspace=workspace, runs_dir=runs_dir)
    url = f"http://{host}:{port}"
    if open_browser and _is_localhost(host):
        webbrowser.open(url)
    app.run(host=host, port=port, debug=False, threaded=True)


def _is_localhost(host: str) -> bool:
    if host in {"127.0.0.1", "localhost", "::1"}:
        return True
    try:
        return socket.gethostbyname(host) == "127.0.0.1"
    except Exception:
        return False


INDEX_HTML = r"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Lumibot Studio</title>
  <style>
    :root {
      --bg: #f7f7f4;
      --ink: #1f2933;
      --muted: #64748b;
      --line: #d8ded8;
      --panel: #ffffff;
      --accent: #146c5f;
      --accent-2: #375a7f;
      --warn: #9a6515;
      --fail: #a73535;
      --pass: #20724d;
      --shadow: 0 1px 2px rgba(18, 32, 44, 0.08);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: var(--bg);
      letter-spacing: 0;
    }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 14px 20px;
      border-bottom: 1px solid var(--line);
      background: #ffffff;
      position: sticky;
      top: 0;
      z-index: 10;
    }
    h1 { font-size: 18px; margin: 0; font-weight: 700; }
    h2 { font-size: 16px; margin: 0 0 12px; }
    h3 { font-size: 14px; margin: 16px 0 8px; }
    nav { display: flex; gap: 4px; }
    nav button, .button {
      border: 1px solid var(--line);
      background: #fff;
      color: var(--ink);
      min-height: 36px;
      padding: 7px 11px;
      border-radius: 6px;
      cursor: pointer;
      font-size: 14px;
    }
    nav button.active, .button.primary {
      border-color: var(--accent);
      background: var(--accent);
      color: #fff;
    }
    button:disabled { opacity: 0.55; cursor: not-allowed; }
    main { padding: 18px 20px 32px; max-width: 1280px; margin: 0 auto; }
    .view { display: none; }
    .view.active { display: block; }
    .grid { display: grid; gap: 14px; grid-template-columns: minmax(280px, 420px) 1fr; align-items: start; }
    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      padding: 14px;
    }
    label { display: block; font-size: 12px; color: var(--muted); margin: 10px 0 5px; }
    input, select, textarea {
      width: 100%;
      min-height: 36px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--ink);
      padding: 7px 9px;
      font: inherit;
    }
    textarea { min-height: 110px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }
    .row { display: grid; gap: 10px; grid-template-columns: 1fr 1fr; }
    .toolbar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-top: 12px; }
    .checks { display: grid; gap: 8px; }
    .check {
      border: 1px solid var(--line);
      border-left-width: 5px;
      border-radius: 6px;
      padding: 9px 10px;
      background: #fff;
    }
    .check.pass { border-left-color: var(--pass); }
    .check.warn { border-left-color: var(--warn); }
    .check.fail { border-left-color: var(--fail); }
    .muted { color: var(--muted); font-size: 12px; }
    .metric-grid { display: grid; gap: 10px; grid-template-columns: repeat(4, minmax(120px, 1fr)); }
    .metric { border: 1px solid var(--line); border-radius: 8px; padding: 11px; background: #fff; }
    .metric .value { font-size: 20px; font-weight: 700; margin-top: 4px; }
    pre {
      max-height: 360px;
      overflow: auto;
      background: #101923;
      color: #eef6f2;
      padding: 12px;
      border-radius: 8px;
      font-size: 12px;
      line-height: 1.45;
    }
    table { width: 100%; border-collapse: collapse; font-size: 12px; }
    th, td { border-bottom: 1px solid var(--line); padding: 7px; text-align: left; vertical-align: top; }
    th { color: var(--muted); font-weight: 650; }
    .status-pill {
      display: inline-flex;
      min-width: 80px;
      justify-content: center;
      border-radius: 999px;
      padding: 4px 9px;
      background: #eef2f1;
      font-size: 12px;
      font-weight: 650;
    }
    .status-pill.completed { color: var(--pass); }
    .status-pill.failed { color: var(--fail); }
    .status-pill.running { color: var(--accent-2); }
    .status-pill.canceled { color: var(--warn); }
    progress { width: 100%; height: 12px; }
    iframe {
      width: 100%;
      min-height: 520px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
    }
    canvas {
      width: 100%;
      height: 260px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
    }
    .artifact-list { display: flex; flex-wrap: wrap; gap: 8px; }
    .artifact-list a { color: var(--accent-2); text-decoration: none; border: 1px solid var(--line); border-radius: 6px; padding: 6px 8px; background: #fff; }
    .hide { display: none; }
    @media (max-width: 900px) {
      header { align-items: flex-start; gap: 10px; flex-direction: column; }
      nav { flex-wrap: wrap; }
      .grid, .row, .metric-grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <header>
    <h1>Lumibot Studio</h1>
    <nav>
      <button data-view="setup" class="active">Setup</button>
      <button data-view="running">Running</button>
      <button data-view="results">Results</button>
      <button data-view="history">History</button>
      <button data-view="settings">Settings</button>
    </nav>
  </header>
  <main>
    <section id="setup" class="view active">
      <div class="grid">
        <form id="run-form" class="panel">
          <h2>Setup</h2>
          <label>Strategy source</label>
          <select id="strategy-source">
            <option value="template">Template</option>
            <option value="file">Python file</option>
          </select>
          <div id="template-controls">
            <label>Template</label>
            <select id="template-id"></select>
          </div>
          <div id="file-controls" class="hide">
            <label>Strategy file</label>
            <input id="strategy-path" placeholder="/path/to/strategy.py">
            <label>Strategy class</label>
            <select id="strategy-class"></select>
          </div>
          <label>Data source</label>
          <select id="data-source">
            <option value="yahoo">Yahoo</option>
            <option value="pandas_csv">Pandas/CSV</option>
          </select>
          <div class="row">
            <div>
              <label>Symbol</label>
              <input id="symbol" value="SPY">
            </div>
            <div>
              <label>Benchmark</label>
              <input id="benchmark" value="SPY">
            </div>
          </div>
          <div id="csv-controls" class="hide">
            <label>CSV path</label>
            <input id="csv-path" placeholder="/path/to/data.csv">
            <div class="row">
              <div>
                <label>Datetime column</label>
                <input id="datetime-column" value="datetime">
              </div>
              <div>
                <label>Timezone</label>
                <input id="timezone" value="America/New_York">
              </div>
            </div>
          </div>
          <div class="row">
            <div>
              <label>Start</label>
              <input id="start" type="date" value="2024-01-01">
            </div>
            <div>
              <label>End</label>
              <input id="end" type="date" value="2024-12-31">
            </div>
          </div>
          <div class="row">
            <div>
              <label>Budget</label>
              <input id="budget" type="number" value="100000" min="1">
            </div>
            <div>
              <label>Risk-free rate</label>
              <input id="risk-free-rate" type="number" step="0.0001" placeholder="0.0">
            </div>
          </div>
          <label>Parameters JSON</label>
          <textarea id="parameters">{ "symbol": "SPY" }</textarea>
          <div class="toolbar">
            <button type="button" class="button" id="preflight-button">Preflight</button>
            <button type="submit" class="button primary" id="run-button">Run</button>
          </div>
        </form>
        <div class="panel">
          <h2>Preflight</h2>
          <div id="preflight" class="checks"></div>
        </div>
      </div>
    </section>

    <section id="running" class="view">
      <div class="panel">
        <h2>Running</h2>
        <div id="run-status"></div>
        <progress id="progress" value="0" max="100"></progress>
        <div class="toolbar">
          <button class="button" id="cancel-button">Cancel</button>
          <button class="button" id="refresh-button">Refresh</button>
        </div>
        <h3>Logs</h3>
        <pre id="logs"></pre>
        <h3>Artifacts</h3>
        <div id="running-artifacts" class="artifact-list"></div>
      </div>
    </section>

    <section id="results" class="view">
      <div class="panel">
        <h2>Results</h2>
        <div id="metrics" class="metric-grid"></div>
        <h3>Equity</h3>
        <canvas id="equity-chart" width="900" height="260"></canvas>
        <h3>Drawdown</h3>
        <canvas id="drawdown-chart" width="900" height="220"></canvas>
        <h3>Trades</h3>
        <div class="toolbar">
          <button class="button" id="trades-prev">Prev</button>
          <button class="button" id="trades-next">Next</button>
        </div>
        <div id="trades-table"></div>
        <h3>Logs</h3>
        <pre id="result-logs"></pre>
        <h3>HTML Artifacts</h3>
        <select id="html-artifact"></select>
        <iframe id="html-frame"></iframe>
        <h3>Downloads</h3>
        <div id="result-artifacts" class="artifact-list"></div>
      </div>
    </section>

    <section id="history" class="view">
      <div class="panel">
        <h2>History</h2>
        <input id="history-search" placeholder="Search">
        <div id="history-table"></div>
      </div>
    </section>

    <section id="settings" class="view">
      <div class="panel">
        <h2>Settings</h2>
        <table>
          <tbody>
            <tr><th>Workspace</th><td id="setting-workspace"></td></tr>
            <tr><th>Runs directory</th><td id="setting-runs-dir"></td></tr>
            <tr><th>Default benchmark</th><td>SPY</td></tr>
            <tr><th>Default budget</th><td>100000</td></tr>
            <tr><th>Artifact retention</th><td>Keep all</td></tr>
          </tbody>
        </table>
      </div>
    </section>
  </main>
  <script>
    const state = { templates: [], currentRunId: null, logOffset: 0, tradesOffset: 0, poll: null };
    const $ = (id) => document.getElementById(id);

    function showView(name) {
      document.querySelectorAll(".view").forEach(v => v.classList.toggle("active", v.id === name));
      document.querySelectorAll("nav button").forEach(b => b.classList.toggle("active", b.dataset.view === name));
      if (name === "history") loadHistory();
      if (name === "results" && state.currentRunId) loadResults();
    }

    document.querySelectorAll("nav button").forEach(button => {
      button.addEventListener("click", () => showView(button.dataset.view));
    });

    async function api(path, options = {}) {
      const response = await fetch(path, {
        headers: { "Content-Type": "application/json" },
        ...options
      });
      const text = await response.text();
      const payload = text ? JSON.parse(text) : {};
      if (!response.ok) throw new Error(payload.error || response.statusText);
      return payload;
    }

    function buildSpec() {
      let parameters = {};
      try { parameters = JSON.parse($("parameters").value || "{}"); }
      catch (error) { throw new Error("Parameters JSON is invalid."); }
      return {
        strategy: {
          source: $("strategy-source").value,
          template_id: $("template-id").value,
          path: $("strategy-path").value,
          class_name: $("strategy-class").value
        },
        data_source: {
          type: $("data-source").value,
          symbol: $("symbol").value,
          csv_path: $("csv-path").value,
          datetime_column: $("datetime-column").value,
          timezone: $("timezone").value
        },
        backtest: {
          start: $("start").value,
          end: $("end").value,
          budget: Number($("budget").value),
          benchmark_asset: $("benchmark").value,
          risk_free_rate: $("risk-free-rate").value === "" ? null : Number($("risk-free-rate").value)
        },
        parameters,
        outputs: {
          show_plot: true,
          show_indicators: true,
          save_tearsheet: true,
          save_logfile: false
        }
      };
    }

    function renderChecks(checks) {
      $("preflight").innerHTML = (checks || []).map(check => `
        <div class="check ${check.status}">
          <strong>${escapeHtml(check.title)}</strong>
          <div class="muted">${escapeHtml(check.detail || "")}</div>
        </div>`).join("");
    }

    async function runPreflight() {
      const payload = await api("/api/preflight", { method: "POST", body: JSON.stringify(buildSpec()) });
      renderChecks(payload.checks);
    }

    async function submitRun(event) {
      event.preventDefault();
      const payload = await api("/api/runs", { method: "POST", body: JSON.stringify(buildSpec()) });
      state.currentRunId = payload.run_id;
      state.logOffset = 0;
      showView("running");
      startPolling();
    }

    function startPolling() {
      if (state.poll) clearInterval(state.poll);
      refreshRun();
      state.poll = setInterval(refreshRun, 1200);
    }

    async function refreshRun() {
      if (!state.currentRunId) return;
      const run = await api(`/api/runs/${state.currentRunId}`);
      renderRunStatus(run.status);
      await loadLogs("logs");
      if (["completed", "failed", "canceled"].includes(run.status.state)) {
        clearInterval(state.poll);
        state.poll = null;
        await loadResults();
      }
    }

    function renderRunStatus(status) {
      $("run-status").innerHTML = `
        <p><span class="status-pill ${status.state}">${status.state}</span> ${escapeHtml(status.phase || "")}</p>
        <p class="muted">Current date: ${escapeHtml(status.current_datetime || "-")}</p>
        <p class="muted">${escapeHtml(status.error_summary || "")}</p>`;
      $("progress").value = status.progress_pct || 0;
      renderArtifacts(status.artifacts || [], "running-artifacts");
    }

    async function loadLogs(targetId) {
      if (!state.currentRunId) return;
      const payload = await api(`/api/runs/${state.currentRunId}/logs?offset=${targetId === "logs" ? state.logOffset : 0}`);
      if (targetId === "logs") {
        $("logs").textContent += payload.text;
        state.logOffset = payload.next_offset;
        $("logs").scrollTop = $("logs").scrollHeight;
      } else {
        $(targetId).textContent = payload.text;
      }
    }

    async function loadResults() {
      if (!state.currentRunId) return;
      const run = await api(`/api/runs/${state.currentRunId}`);
      renderMetrics(run.status.metrics_summary || {});
      renderArtifacts(run.status.artifacts || [], "result-artifacts");
      renderHtmlArtifacts(run.status.artifacts || []);
      await loadLogs("result-logs");
      await loadTable();
      await loadCharts();
    }

    function renderMetrics(metrics) {
      const labels = [
        ["total_return", "Total Return", "pct"],
        ["cagr", "CAGR", "pct"],
        ["sharpe", "Sharpe", "num"],
        ["sortino", "Sortino", "num"],
        ["volatility", "Volatility", "pct"],
        ["max_drawdown", "Max Drawdown", "pct"],
        ["win_rate", "Win Rate", "pct"],
        ["number_of_trades", "Trades", "int"],
        ["final_portfolio_value", "Final Value", "money"],
        ["runtime_seconds", "Runtime", "sec"]
      ];
      $("metrics").innerHTML = labels.map(([key, label, type]) => `
        <div class="metric"><div class="muted">${label}</div><div class="value">${formatMetric(metrics[key], type)}</div></div>
      `).join("");
    }

    function renderArtifacts(artifacts, targetId) {
      $(targetId).innerHTML = artifacts.map(artifact => `
        <a href="/api/runs/${state.currentRunId}/artifacts/${encodeURIComponent(artifact.name)}" target="_blank">
          ${escapeHtml(artifact.name)}
        </a>`).join("");
    }

    function renderHtmlArtifacts(artifacts) {
      const htmlArtifacts = artifacts.filter(a => a.kind === "html");
      $("html-artifact").innerHTML = htmlArtifacts.map(a => `<option value="${escapeHtml(a.name)}">${escapeHtml(a.name)}</option>`).join("");
      const first = htmlArtifacts[0];
      $("html-frame").src = first ? `/api/runs/${state.currentRunId}/artifacts/${encodeURIComponent(first.name)}` : "about:blank";
    }

    async function loadTable() {
      try {
        const payload = await api(`/api/runs/${state.currentRunId}/table/trades.csv?offset=${state.tradesOffset}&limit=50`);
        const head = payload.columns.map(c => `<th>${escapeHtml(c)}</th>`).join("");
        const rows = payload.rows.map(row => `<tr>${payload.columns.map(c => `<td>${escapeHtml(row[c] || "")}</td>`).join("")}</tr>`).join("");
        $("trades-table").innerHTML = `<table><thead><tr>${head}</tr></thead><tbody>${rows}</tbody></table>`;
      } catch (error) {
        $("trades-table").innerHTML = `<p class="muted">${escapeHtml(error.message)}</p>`;
      }
    }

    async function loadCharts() {
      const payload = await api(`/api/runs/${state.currentRunId}/chart-data`);
      drawLineChart($("equity-chart"), payload.equity || [], "portfolio_value", "#146c5f");
      drawLineChart($("drawdown-chart"), payload.drawdown || [], "drawdown", "#a73535");
    }

    function drawLineChart(canvas, rows, key, color) {
      const ctx = canvas.getContext("2d");
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      if (!rows.length) {
        ctx.fillStyle = "#64748b";
        ctx.fillText("No chart data", 18, 28);
        return;
      }
      const values = rows.map(row => Number(row[key])).filter(v => Number.isFinite(v));
      const min = Math.min(...values);
      const max = Math.max(...values);
      const pad = 22;
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.beginPath();
      rows.forEach((row, index) => {
        const value = Number(row[key]);
        const x = pad + (index / Math.max(1, rows.length - 1)) * (canvas.width - pad * 2);
        const y = canvas.height - pad - ((value - min) / Math.max(0.000001, max - min)) * (canvas.height - pad * 2);
        if (index === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();
    }

    async function loadHistory() {
      const payload = await api("/api/runs");
      const query = $("history-search").value.toLowerCase();
      const runs = payload.runs.filter(run => JSON.stringify(run).toLowerCase().includes(query));
      $("history-table").innerHTML = `<table><thead><tr><th>Run</th><th>Status</th><th>Progress</th><th></th></tr></thead><tbody>
        ${runs.map(run => `<tr>
          <td>${escapeHtml(run.run_id)}</td>
          <td><span class="status-pill ${run.state}">${escapeHtml(run.state)}</span></td>
          <td>${formatMetric(run.progress_pct, "num")}</td>
          <td><button class="button" data-run="${escapeHtml(run.run_id)}">Open</button></td>
        </tr>`).join("")}
      </tbody></table>`;
      document.querySelectorAll("[data-run]").forEach(button => {
        button.addEventListener("click", () => {
          state.currentRunId = button.dataset.run;
          showView("results");
        });
      });
    }

    async function init() {
      const health = await api("/api/health");
      $("setting-workspace").textContent = health.workspace;
      $("setting-runs-dir").textContent = health.runs_dir;
      const payload = await api("/api/templates");
      state.templates = payload.templates;
      $("template-id").innerHTML = state.templates.map(t => `<option value="${t.template_id}">${escapeHtml(t.name)}</option>`).join("");
      applyTemplateDefaults();
      await loadHistory();
    }

    function applyTemplateDefaults() {
      const template = state.templates.find(t => t.template_id === $("template-id").value);
      if (!template) return;
      $("symbol").value = template.default_symbol || "SPY";
      $("parameters").value = JSON.stringify(template.default_parameters || {}, null, 2);
      $("strategy-class").innerHTML = `<option value="${template.class_name}">${template.class_name}</option>`;
    }

    async function discoverFileClasses() {
      if (!$("strategy-path").value) return;
      const payload = await api("/api/strategies/discover", { method: "POST", body: JSON.stringify({ path: $("strategy-path").value }) });
      $("strategy-class").innerHTML = payload.classes.map(c => `<option value="${c.class_name}">${c.class_name}</option>`).join("");
    }

    function formatMetric(value, type) {
      if (value === null || value === undefined || value === "") return "-";
      const number = Number(value);
      if (Number.isFinite(number)) {
        if (type === "pct") return `${(number * 100).toFixed(2)}%`;
        if (type === "money") return `$${number.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
        if (type === "sec") return `${number.toFixed(1)}s`;
        if (type === "int") return `${Math.round(number)}`;
        return number.toFixed(3);
      }
      return String(value);
    }

    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>"']/g, char => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
      }[char]));
    }

    $("run-form").addEventListener("submit", submitRun);
    $("preflight-button").addEventListener("click", () => runPreflight().catch(error => renderChecks([{ status: "fail", title: "Preflight", detail: error.message }])));
    $("cancel-button").addEventListener("click", () => state.currentRunId && api(`/api/runs/${state.currentRunId}/cancel`, { method: "POST" }).then(refreshRun));
    $("refresh-button").addEventListener("click", refreshRun);
    $("template-id").addEventListener("change", applyTemplateDefaults);
    $("strategy-source").addEventListener("change", () => {
      $("template-controls").classList.toggle("hide", $("strategy-source").value !== "template");
      $("file-controls").classList.toggle("hide", $("strategy-source").value !== "file");
    });
    $("data-source").addEventListener("change", () => {
      $("csv-controls").classList.toggle("hide", $("data-source").value !== "pandas_csv");
    });
    $("strategy-path").addEventListener("change", () => discoverFileClasses().catch(() => {}));
    $("history-search").addEventListener("input", loadHistory);
    $("trades-prev").addEventListener("click", () => { state.tradesOffset = Math.max(0, state.tradesOffset - 50); loadTable(); });
    $("trades-next").addEventListener("click", () => { state.tradesOffset += 50; loadTable(); });
    $("html-artifact").addEventListener("change", () => {
      $("html-frame").src = `/api/runs/${state.currentRunId}/artifacts/${encodeURIComponent($("html-artifact").value)}`;
    });
    init().catch(error => renderChecks([{ status: "fail", title: "Startup", detail: error.message }]));
  </script>
</body>
</html>
"""
