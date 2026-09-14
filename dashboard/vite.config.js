import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { spawn } from 'child_process';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const REPO_ROOT = path.resolve(__dirname, '..');

export default defineConfig({
  plugins: [
    react(),
    {
      name: 'icvfx-api-middleware',
      configureServer(server) {
        server.middlewares.use(async (req, res, next) => {
          const readJsonBody = () =>
            new Promise((resolve) => {
              let data = '';
              req.on('data', (chunk) => (data += chunk));
              req.on('end', () => {
                try {
                  resolve(JSON.parse(data));
                } catch {
                  resolve({});
                }
              });
            });

          if (req.url.startsWith('/api/data')) {
            try {
              const scenarios = ['occlusion', 'ptp_jitter', 'dropped_frame'];
              const incidents = {};
              for (const s of scenarios) {
                const p = path.join(REPO_ROOT, 'runs', s, 'incident_report.json');
                if (fs.existsSync(p)) {
                  incidents[s] = JSON.parse(fs.readFileSync(p, 'utf8'));
                }
              }
              const statePath = path.join(REPO_ROOT, 'mcp-remediation', 'stage_state.json');
              let stageState = {};
              if (fs.existsSync(statePath)) {
                stageState = JSON.parse(fs.readFileSync(statePath, 'utf8'));
              }
              res.setHeader('Content-Type', 'application/json');
              res.end(JSON.stringify({ incidents, stageState }));
            } catch (err) {
              res.statusCode = 500;
              res.end(JSON.stringify({ error: err.message }));
            }
            return;
          }

          if (req.url.startsWith('/api/udp-telemetry')) {
            try {
              const fetchRes = await fetch('http://127.0.0.1:8080/api/udp-telemetry');
              const data = await fetchRes.json();
              res.setHeader('Content-Type', 'application/json');
              res.end(JSON.stringify(data));
            } catch (err) {
              res.statusCode = 502;
              res.end(JSON.stringify({ ok: false, error: err.message }));
            }
            return;
          }

          if (req.url.startsWith('/api/inject-fault') && req.method === 'POST') {
            try {
              const body = await readJsonBody();
              const fetchRes = await fetch('http://127.0.0.1:8080/api/inject-fault', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
              });
              const data = await fetchRes.json();
              res.setHeader('Content-Type', 'application/json');
              res.end(JSON.stringify(data));
            } catch (err) {
              res.statusCode = 200;
              res.end(JSON.stringify({ ok: true, fallback: true }));
            }
            return;
          }

          if (req.url.startsWith('/api/set-filter-mode') && req.method === 'POST') {
            try {
              const body = await readJsonBody();
              const fetchRes = await fetch('http://127.0.0.1:8080/api/set-filter-mode', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
              });
              const data = await fetchRes.json();
              res.setHeader('Content-Type', 'application/json');
              res.end(JSON.stringify(data));
            } catch (err) {
              res.statusCode = 200;
              res.end(JSON.stringify({ ok: true, fallback: true }));
            }
            return;
          }

          if (req.url.startsWith('/api/simulate') && req.method === 'POST') {
            try {
              const py = spawn('python', ['orchestrator/run_fault_injection_test.py'], {
                cwd: REPO_ROOT,
              });
              let stdout = '';
              let stderr = '';
              py.stdout.on('data', (d) => { stdout += d.toString(); });
              py.stderr.on('data', (d) => { stderr += d.toString(); });
              py.on('close', (code) => {
                res.setHeader('Content-Type', 'application/json');
                res.end(JSON.stringify({ code, stdout, stderr }));
              });
            } catch (err) {
              res.statusCode = 500;
              res.end(JSON.stringify({ error: err.message }));
            }
            return;
          }

          if (req.url.startsWith('/api/custom-action') && req.method === 'POST') {
            try {
              const body = await readJsonBody();
              const tool = body.tool || 'notify_stage_hud';
              const argsStr = JSON.stringify(body.args || {});
              const py = spawn('python', ['orchestrator/run_custom_action.py', '--action', 'mcp', '--tool', tool, '--args', argsStr], {
                cwd: REPO_ROOT,
              });
              let stdout = '';
              let stderr = '';
              py.stdout.on('data', (d) => { stdout += d.toString(); });
              py.stderr.on('data', (d) => { stderr += d.toString(); });
              py.on('close', () => {
                res.setHeader('Content-Type', 'application/json');
                const match = stdout.match(/\{[\s\S]*\}/);
                if (match) {
                  res.end(match[0]);
                } else {
                  res.end(JSON.stringify({ stdout, stderr }));
                }
              });
            } catch (err) {
              res.statusCode = 500;
              res.end(JSON.stringify({ error: err.message }));
            }
            return;
          }

          if (req.url.startsWith('/api/custom-diagnose') && req.method === 'POST') {
            try {
              const body = await readJsonBody();
              const scenario = body.scenario || 'occlusion';
              const camera = String(body.camera || 1);
              const anomalies = String(body.anomalies !== undefined && body.anomalies !== null ? body.anomalies : 0);
              const summary = body.summary || '';
              const prompt = body.prompt || '';

              const args = [
                'orchestrator/run_custom_action.py',
                '--action', 'diagnose',
                '--scenario', scenario,
                '--camera', camera,
                '--anomalies', anomalies,
                '--summary', summary,
                '--prompt', prompt,
              ];

              if (body.jitter !== undefined && body.jitter !== null) {
                args.push('--jitter', String(body.jitter));
              }
              if (body.render_frozen !== undefined && body.render_frozen !== null) {
                args.push('--render_frozen', String(body.render_frozen));
              }

              if (body.image_base64 && typeof body.image_base64 === 'string') {
                try {
                  const base64Data = body.image_base64.replace(/^data:image\/\w+;base64,/, '');
                  const buffer = Buffer.from(base64Data, 'base64');
                  if (buffer && buffer.length > 0) {
                    const uploadDir = path.join(REPO_ROOT, 'runs', 'custom');
                    if (!fs.existsSync(uploadDir)) fs.mkdirSync(uploadDir, { recursive: true });
                    const uploadPath = path.join(uploadDir, 'custom_uploaded_frame.png');
                    fs.writeFileSync(uploadPath, buffer);
                    args.push('--witness_image', uploadPath);

                    const publicDir = path.join(__dirname, 'public', 'runs', 'custom');
                    if (!fs.existsSync(publicDir)) fs.mkdirSync(publicDir, { recursive: true });
                    fs.writeFileSync(path.join(publicDir, 'custom_uploaded_frame.png'), buffer);
                  }
                } catch (imgErr) {
                  console.warn('Image base64 decode warning:', imgErr);
                }
              } else if (body.image_path && typeof body.image_path === 'string') {
                const rawP = body.image_path.replace(/^[/\\]+/, '');
                let candidate = path.join(REPO_ROOT, rawP);
                if (!fs.existsSync(candidate)) {
                  candidate = path.join(__dirname, 'public', rawP);
                }
                if (fs.existsSync(candidate)) {
                  args.push('--witness_image', candidate);
                }
              }

              const py = spawn('python', args, {
                cwd: REPO_ROOT,
              });
              let stdout = '';
              let stderr = '';
              py.stdout.on('data', (d) => { stdout += d.toString(); });
              py.stderr.on('data', (d) => { stderr += d.toString(); });
              py.on('close', () => {
                res.setHeader('Content-Type', 'application/json');
                const match = stdout.match(/\{[\s\S]*\}/);
                if (match) {
                  res.end(match[0]);
                } else {
                  res.end(JSON.stringify({ stdout, stderr }));
                }
              });
            } catch (err) {
              res.statusCode = 500;
              res.end(JSON.stringify({ error: err.message }));
            }
            return;
          }

          if (req.url.startsWith('/api/process-video') && req.method === 'POST') {
            try {
              const body = await readJsonBody();
              const scenario = body.scenario || 'occlusion';
              const camera = String(body.camera || 1);
              const anomalies = String(body.anomalies !== undefined && body.anomalies !== null ? body.anomalies : 35);
              const summary = body.summary || '';
              const jitter = String(body.jitter !== undefined && body.jitter !== null ? body.jitter : 0.18);
              const render_frozen = String(Boolean(body.render_frozen));

              let inputVideoPath = body.video_path || 'dashboard/public/videos/stage_witness_boom_occlusion.mp4';

              if (body.video_base64 && typeof body.video_base64 === 'string') {
                try {
                  const b64Data = body.video_base64.replace(/^data:video\/\w+;base64,/, '');
                  const buf = Buffer.from(b64Data, 'base64');
                  if (buf && buf.length > 0) {
                    const uploadDir = path.join(__dirname, 'public', 'videos', 'uploads');
                    if (!fs.existsSync(uploadDir)) fs.mkdirSync(uploadDir, { recursive: true });
                    const uploadFilename = `custom_video_${Date.now()}.mp4`;
                    const uploadFilePath = path.join(uploadDir, uploadFilename);
                    fs.writeFileSync(uploadFilePath, buf);
                    inputVideoPath = uploadFilePath;
                  }
                } catch (vErr) {
                  console.warn('Video base64 decode warning:', vErr);
                }
              }

              const processedDir = path.join(__dirname, 'public', 'videos', 'processed');
              if (!fs.existsSync(processedDir)) fs.mkdirSync(processedDir, { recursive: true });
              const outputFilename = `remediated_${scenario}_${Date.now()}.mp4`;
              const outputVideoPath = path.join(processedDir, outputFilename);

              const args = [
                'orchestrator/video_remediator.py',
                '--input_video', inputVideoPath,
                '--output_video', outputVideoPath,
                '--scenario', scenario,
                '--camera', camera,
                '--anomalies', anomalies,
                '--jitter', jitter,
                '--render_frozen', render_frozen,
                '--summary', summary,
              ];

              const py = spawn('python', args, { cwd: REPO_ROOT });
              let stdout = '';
              let stderr = '';
              py.stdout.on('data', (d) => { stdout += d.toString(); });
              py.stderr.on('data', (d) => { stderr += d.toString(); });
              py.on('close', () => {
                res.setHeader('Content-Type', 'application/json');
                const match = stdout.match(/\{[\s\S]*\}/);
                if (match) {
                  res.end(match[0]);
                } else {
                  res.end(JSON.stringify({ stdout, stderr }));
                }
              });
            } catch (err) {
              res.statusCode = 500;
              res.end(JSON.stringify({ error: err.message }));
            }
            return;
          }

          if (req.url.startsWith('/api/grafana-stream/status')) {
            try {
              const statusPath = path.join(REPO_ROOT, 'runs', 'grafana_shipper.json');
              if (fs.existsSync(statusPath)) {
                const data = JSON.parse(fs.readFileSync(statusPath, 'utf8'));
                res.setHeader('Content-Type', 'application/json');
                res.end(JSON.stringify({ ok: true, ...data }));
              } else {
                res.setHeader('Content-Type', 'application/json');
                res.end(JSON.stringify({ ok: true, running: false, status: 'IDLE', pushes_sent: 0 }));
              }
            } catch (err) {
              res.setHeader('Content-Type', 'application/json');
              res.end(JSON.stringify({ ok: false, error: err.message }));
            }
            return;
          }

          if (req.url.startsWith('/api/grafana-stream/start') && req.method === 'POST') {
            try {
              const body = await readJsonBody();
              const interval = String(body.interval || 5.0);
              const py = spawn('python', ['scripts/push_to_grafana_cloud.py', '--start', '--interval', interval], {
                cwd: REPO_ROOT,
              });
              let stdout = '';
              let stderr = '';
              py.stdout.on('data', (d) => { stdout += d.toString(); });
              py.stderr.on('data', (d) => { stderr += d.toString(); });
              py.on('close', (code) => {
                res.setHeader('Content-Type', 'application/json');
                res.end(JSON.stringify({ ok: code === 0, code, stdout, stderr }));
              });
            } catch (err) {
              res.statusCode = 500;
              res.end(JSON.stringify({ ok: false, error: err.message }));
            }
            return;
          }

          if (req.url.startsWith('/api/grafana-stream/stop') && req.method === 'POST') {
            try {
              const py = spawn('python', ['scripts/push_to_grafana_cloud.py', '--stop'], {
                cwd: REPO_ROOT,
              });
              let stdout = '';
              let stderr = '';
              py.stdout.on('data', (d) => { stdout += d.toString(); });
              py.stderr.on('data', (d) => { stderr += d.toString(); });
              py.on('close', (code) => {
                res.setHeader('Content-Type', 'application/json');
                res.end(JSON.stringify({ ok: code === 0, code, stdout, stderr }));
              });
            } catch (err) {
              res.statusCode = 500;
              res.end(JSON.stringify({ ok: false, error: err.message }));
            }
            return;
          }

          next();
        });
      },
    },
  ],
  server: {
    port: 5173,
    host: true,
  },
});
