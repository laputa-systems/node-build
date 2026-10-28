from __future__ import annotations

import json
import subprocess
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path


class SmokeError(Exception):
    pass


@dataclass(frozen=True)
class SmokeFinding:
    name: str
    ok: bool
    detail: str


CHECK_TIMEOUT = 60

EXPECTED_IDENTITY = {
    "aarch64-apple-darwin": "arm64/darwin",
    "x86_64-unknown-linux-musl": "x64/linux",
}


def run_node(node: Path, args: list[str], cwd: Path, extra_env: dict | None = None) -> subprocess.CompletedProcess:
    import os

    env = dict(os.environ)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [str(node), *args], cwd=cwd, env=env,
        capture_output=True, text=True, timeout=CHECK_TIMEOUT, check=False,
    )


def check_version(node: Path, work: Path, fixtures: Path) -> str:
    completed = run_node(node, ["--version"], work)
    if completed.returncode != 0:
        raise SmokeError(f"--version failed: {completed.stderr}")
    version = completed.stdout.strip()
    if version != "v26.12.1":
        raise SmokeError(f"version {version} != v26.12.1")
    return version


def check_arch(node: Path, work: Path, fixtures: Path, triple: str = "aarch64-apple-darwin") -> str:
    completed = run_node(node, ["-p", "process.arch + '/' + process.platform"], work)
    identity = completed.stdout.strip()
    expected = EXPECTED_IDENTITY[triple]
    if identity != expected:
        raise SmokeError(f"identity {identity} != {expected}")
    return identity


def check_modules(node: Path, work: Path, fixtures: Path) -> str:
    script = (
        "const cjs = require('./hello.cjs');"
        "import('./hello.mjs').then((esm) => {"
        "  if (cjs.answer !== 42 || esm.answer !== 42) { process.exit(1); }"
        "  console.log('cjs+esm ok');"
        "});"
    )
    completed = run_node(node, ["-e", script], fixtures / "smoke")
    if completed.returncode != 0 or "cjs+esm ok" not in completed.stdout:
        raise SmokeError(f"module check failed: {completed.stderr}")
    return "cjs+esm ok"


def check_node_test(node: Path, work: Path, fixtures: Path) -> str:
    completed = run_node(node, ["--test", "sample.test.js"], fixtures / "smoke")
    if completed.returncode != 0:
        raise SmokeError(f"node:test failed: {completed.stdout}{completed.stderr}")
    if "pass 1" not in completed.stdout:
        raise SmokeError(f"node:test unexpected output: {completed.stdout}")
    return "pass 1"


def check_fs_async(node: Path, work: Path, fixtures: Path) -> str:
    script = (
        "const fs = require('node:fs/promises');"
        "(async () => {"
        "  await fs.writeFile('probe.txt', 'x'.repeat(1000));"
        "  const data = await fs.readFile('probe.txt', 'utf8');"
        "  if (data.length !== 1000) { process.exit(1); }"
        "  console.log('fs ok');"
        "})();"
    )
    completed = run_node(node, ["-e", script], work)
    if completed.returncode != 0 or "fs ok" not in completed.stdout:
        raise SmokeError(f"fs check failed: {completed.stderr}")
    return "fs ok"


def check_dns_tcp(node: Path, work: Path, fixtures: Path) -> str:
    script = (
        "const dns = require('node:dns/promises');"
        "const net = require('node:net');"
        "(async () => {"
        "  await dns.lookup('localhost');"
        "  const server = net.createServer((socket) => { socket.end('pong'); });"
        "  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));"
        "  const port = server.address().port;"
        "  const data = await new Promise((resolve, reject) => {"
        "    let buf = '';"
        "    const client = net.connect(port, '127.0.0.1', () => {});"
        "    client.on('data', (chunk) => { buf += chunk; });"
        "    client.on('end', () => resolve(buf));"
        "    client.on('error', reject);"
        "  });"
        "  server.close();"
        "  if (data !== 'pong') { process.exit(1); }"
        "  console.log('dns+tcp ok');"
        "})();"
    )
    completed = run_node(node, ["-e", script], work)
    if completed.returncode != 0 or "dns+tcp ok" not in completed.stdout:
        raise SmokeError(f"dns+tcp check failed: {completed.stderr}")
    return "dns+tcp ok"


def check_http(node: Path, work: Path, fixtures: Path) -> str:
    script = (
        "const http = require('node:http');"
        "(async () => {"
        "  const server = http.createServer((req, res) => { res.end('hello'); });"
        "  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));"
        "  const port = server.address().port;"
        "  const body = await new Promise((resolve, reject) => {"
        "    http.get(`http://127.0.0.1:${port}/`, (res) => {"
        "      let buf = '';"
        "      res.on('data', (c) => { buf += c; });"
        "      res.on('end', () => resolve(buf));"
        "    }).on('error', reject);"
        "  });"
        "  server.close();"
        "  if (body !== 'hello') { process.exit(1); }"
        "  console.log('http ok');"
        "})();"
    )
    completed = run_node(node, ["-e", script], work)
    if completed.returncode != 0 or "http ok" not in completed.stdout:
        raise SmokeError(f"http check failed: {completed.stderr}")
    return "http ok"


def check_https(node: Path, work: Path, fixtures: Path) -> str:
    script_template = (
        "const https = require('node:https');"
        "const fs = require('node:fs');"
        "const options = { key: fs.readFileSync('%s'), cert: fs.readFileSync('%s') };"
        "(async () => {"
        "  const server = https.createServer(options, (req, res) => { res.end('secure'); });"
        "  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));"
        "  const port = server.address().port;"
        "  const trusted = await new Promise((resolve, reject) => {"
        "    https.get({ host: '127.0.0.1', port, path: '/', ca: options.cert, servername: 'localhost' }, (res) => {"
        "      let buf = '';"
        "      res.on('data', (c) => { buf += c; });"
        "      res.on('end', () => resolve(buf));"
        "    }).on('error', reject);"
        "  });"
        "  if (trusted !== 'secure') { process.exit(2); }"
        "  let rejected = false;"
        "  try {"
        "    await new Promise((resolve, reject) => {"
        "      https.get({ host: '127.0.0.1', port, path: '/', servername: 'localhost' }, (res) => {"
        "        res.resume(); res.on('end', () => resolve('unexpected')); }"
        "      ).on('error', reject);"
        "    });"
        "  } catch (error) { rejected = true; }"
        "  server.close();"
        "  if (!rejected) { process.exit(3); }"
        "  console.log('https ok');"
        "})();"
    )
    script = script_template % (
        fixtures / "test-key.pem", fixtures / "test-cert.pem",
    )
    completed = run_node(node, ["-e", script], work)
    if completed.returncode != 0 or "https ok" not in completed.stdout:
        raise SmokeError(f"https check failed ({completed.returncode}): {completed.stderr}")
    return "trusted accepted, untrusted rejected"


def check_crypto(node: Path, work: Path, fixtures: Path) -> str:
    script = (
        "const crypto = require('node:crypto');"
        "(async () => {"
        "  const digest = await crypto.subtle.digest('SHA-256', Buffer.from('abc'));"
        "  const hex = Buffer.from(digest).toString('hex');"
        "  if (hex !== 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad') { process.exit(1); }"
        "  const key = crypto.randomBytes(32);"
        "  const iv = crypto.randomBytes(12);"
        "  const cipher = crypto.createCipheriv('aes-256-gcm', key, iv);"
        "  const enc = Buffer.concat([cipher.update('secret'), cipher.final(), cipher.getAuthTag()]);"
        "  const decipher = crypto.createDecipheriv('aes-256-gcm', key, iv);"
        "  decipher.setAuthTag(enc.subarray(-16));"
        "  const dec = Buffer.concat([decipher.update(enc.subarray(0, -16)), decipher.final()]);"
        "  if (dec.toString() !== 'secret') { process.exit(2); }"
        "  console.log('crypto ok');"
        "})();"
    )
    completed = run_node(node, ["-e", script], work)
    if completed.returncode != 0 or "crypto ok" not in completed.stdout:
        raise SmokeError(f"crypto check failed: {completed.stderr}")
    return "webcrypto vector + aes-gcm roundtrip"


def check_compression(node: Path, work: Path, fixtures: Path) -> str:
    script = (
        "const zlib = require('node:zlib');"
        "const payload = 'x'.repeat(100000);"
        "const deflated = zlib.deflateSync(payload);"
        "if (zlib.inflateSync(deflated).toString() !== payload) { process.exit(1); }"
        "const compressed = zlib.brotliCompressSync(payload);"
        "if (zlib.brotliDecompressSync(compressed).toString() !== payload) { process.exit(2); }"
        "console.log('compression ok');"
    )
    completed = run_node(node, ["-e", script], work)
    if completed.returncode != 0 or "compression ok" not in completed.stdout:
        raise SmokeError(f"compression check failed: {completed.stderr}")
    return "zlib + brotli roundtrips"


def check_fetch_streams(node: Path, work: Path, fixtures: Path) -> str:
    script = (
        "const http = require('node:http');"
        "const { Readable } = require('node:stream');"
        "(async () => {"
        "  const server = http.createServer((req, res) => { Readable.from(['a', 'b']).pipe(res); });"
        "  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));"
        "  const port = server.address().port;"
        "  const response = await fetch(`http://127.0.0.1:${port}/`);"
        "  const text = await response.text();"
        "  server.close();"
        "  if (text !== 'ab') { process.exit(1); }"
        "  console.log('fetch ok');"
        "})();"
    )
    completed = run_node(node, ["-e", script], work)
    if completed.returncode != 0 or "fetch ok" not in completed.stdout:
        raise SmokeError(f"fetch check failed: {completed.stderr}")
    return "fetch ok"


def check_workers_child(node: Path, work: Path, fixtures: Path) -> str:
    script = (
        "const { Worker, isMainThread, parentPort } = require('node:worker_threads');"
        "const { execFile } = require('node:child_process');"
        "if (!isMainThread) { parentPort.postMessage(21 * 2); process.exit(0); }"
        "(async () => {"
        "  const worker = new Worker(__filename);"
        "  const value = await new Promise((resolve, reject) => {"
        "    worker.on('message', resolve); worker.on('error', reject);"
        "  });"
        "  if (value !== 42) { process.exit(1); }"
        "  const child = await new Promise((resolve, reject) => {"
        f"    execFile('{node}', ['-p', '6*7'], (error, stdout) => {{"
        "      if (error) { reject(error); } else { resolve(stdout.trim()); }"
        "    });"
        "  });"
        "  if (child !== '42') { process.exit(2); }"
        "  console.log('workers ok');"
        "})();"
    )
    probe = work / "worker-probe.cjs"
    probe.write_text(script, encoding="utf-8")
    completed = run_node(node, [str(probe)], work)
    if completed.returncode != 0 or "workers ok" not in completed.stdout:
        raise SmokeError(f"workers check failed: {completed.stderr}")
    return "worker + child ok"


def check_intl(node: Path, work: Path, fixtures: Path) -> str:
    script = (
        "const formatted = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(1234.5);"
        "if (formatted !== '$1,234.50') { process.exit(1); }"
        "const day = new Intl.DateTimeFormat('en-US', { weekday: 'long', timeZone: 'UTC' }).format(new Date('2026-10-26T00:00:00Z'));"
        "if (day !== 'Monday') { process.exit(2); }"
        "console.log('intl ok');"
    )
    completed = run_node(node, ["-e", script], work)
    if completed.returncode != 0 or "intl ok" not in completed.stdout:
        raise SmokeError(f"intl check failed: {completed.stderr}")
    return "en-US currency + weekday"


def check_startup(node: Path, work: Path, fixtures: Path) -> str:
    start = time.monotonic()
    completed = run_node(node, ["-e", "1"], work)
    elapsed_ms = (time.monotonic() - start) * 1000
    if completed.returncode != 0:
        raise SmokeError(f"startup probe failed: {completed.stderr}")
    return f"cold start {elapsed_ms:.0f} ms"


def check_inspector(node: Path, work: Path, fixtures: Path) -> str:
    import re

    probe = work / "inspector-probe.js"
    probe.write_text("setInterval(() => {}, 1000);", encoding="utf-8")
    process = subprocess.Popen(
        [str(node), "--inspect=127.0.0.1:0", str(probe)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        assert process.stderr is not None
        match = None
        deadline = time.monotonic() + 30
        buffered = ""
        while time.monotonic() < deadline and match is None:
            chunk = process.stderr.readline()
            if not chunk:
                break
            buffered += chunk
            match = re.search(r"ws://127\.0\.0\.1:(\d+)/", buffered)
        if match is None:
            raise SmokeError(f"inspector endpoint not announced: {buffered}")
        with urllib.request.urlopen(f"http://127.0.0.1:{match.group(1)}/json/list", timeout=30) as response:
            targets = json.loads(response.read().decode("utf-8"))
        if not targets or "id" not in targets[0]:
            raise SmokeError(f"inspector list unexpected: {targets}")
        return f"inspector target {targets[0]['id'][:8]}"
    finally:
        process.kill()


def check_napi_addon(
    node: Path, work: Path, fixtures: Path, headers: Path,
    triple: str = "aarch64-apple-darwin",
) -> str:
    addon = work / "addon.node"
    if triple == "x86_64-unknown-linux-musl":
        compile_command = [
            "g++", "-shared", "-fPIC",
            f"-I{headers}", str(fixtures / "smoke" / "addon.cc"), "-o", str(addon),
        ]
    else:
        compile_command = [
            "clang++", "-bundle", "-undefined", "dynamic_lookup",
            f"-I{headers}", str(fixtures / "smoke" / "addon.cc"), "-o", str(addon),
        ]
    compile_result = subprocess.run(
        compile_command,
        capture_output=True, text=True, timeout=CHECK_TIMEOUT, check=False,
    )
    if compile_result.returncode != 0:
        raise SmokeError(f"addon compile failed: {compile_result.stderr}")
    script = "const addon = require('./addon.node'); if (addon.answer() !== 42) { process.exit(1); } console.log('addon ok');"
    completed = run_node(node, ["-e", script], work)
    if completed.returncode != 0 or "addon ok" not in completed.stdout:
        raise SmokeError(f"addon load failed: {completed.stderr}")
    return "compiled against shipped headers and loaded"


def check_exclusions(node: Path, work: Path, fixtures: Path, install_root: Path) -> str:
    for name in ("npm", "npx"):
        if (install_root / "bin" / name).exists():
            raise SmokeError(f"excluded payload present: bin/{name}")
    completed = run_node(node, ["--help"], work)
    if completed.returncode != 0 or "Usage: node" not in completed.stdout:
        raise SmokeError(f"--help unexpected: {completed.stdout}{completed.stderr}")
    return "npm/npx absent, --help ok"


CHECKS = (
    ("version", check_version),
    ("arch", check_arch),
    ("modules", check_modules),
    ("node-test", check_node_test),
    ("fs-async", check_fs_async),
    ("dns-tcp", check_dns_tcp),
    ("http", check_http),
    ("https", check_https),
    ("crypto", check_crypto),
    ("compression", check_compression),
    ("fetch-streams", check_fetch_streams),
    ("workers-child", check_workers_child),
    ("intl", check_intl),
    ("startup", check_startup),
    ("inspector", check_inspector),
)


def run_suite(
    node: Path, install_root: Path, headers: Path, work: Path, fixtures: Path,
    triple: str = "aarch64-apple-darwin",
) -> list[SmokeFinding]:
    findings: list[SmokeFinding] = []
    for name, check in CHECKS:
        try:
            if name == "arch":
                detail = check(node, work, fixtures, triple)
            else:
                detail = check(node, work, fixtures)
            findings.append(SmokeFinding(name, True, detail))
        except (SmokeError, subprocess.TimeoutExpired, OSError) as error:
            findings.append(SmokeFinding(name, False, str(error)[:300]))
    try:
        detail = check_napi_addon(node, work, fixtures, headers, triple)
        findings.append(SmokeFinding("napi-addon", True, detail))
    except (SmokeError, subprocess.TimeoutExpired, OSError) as error:
        findings.append(SmokeFinding("napi-addon", False, str(error)[:300]))
    try:
        detail = check_exclusions(node, work, fixtures, install_root)
        findings.append(SmokeFinding("exclusions", True, detail))
    except (SmokeError, subprocess.TimeoutExpired, OSError) as error:
        findings.append(SmokeFinding("exclusions", False, str(error)[:300]))
    return findings
