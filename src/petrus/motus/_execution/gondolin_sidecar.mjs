import net from "node:net";
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath, pathToFileURL } from "node:url";

const VERSION = "0.12.0";
const MAX_FRAME = 8 * 1024 * 1024;
const MAX_OUTPUT = 4 * 1024 * 1024;
const [socketPath, leaseId, workspace, image, ttlText, startupMode] = process.argv.slice(2);
const bootToken = process.env.PETRUS_GONDOLIN_BOOT_TOKEN;
delete process.env.PETRUS_GONDOLIN_BOOT_TOKEN;
if (!bootToken) throw new Error("PETRUS_GONDOLIN_BOOT_TOKEN is required");
const requested = process.env.PETRUS_GONDOLIN_SDK;
if (!requested) throw new Error("PETRUS_GONDOLIN_SDK must explicitly identify Gondolin");
const moduleUrl = requested.startsWith("file:") ? requested : pathToFileURL(path.resolve(requested)).href;
const sdk = await import(moduleUrl);

function installedVersion() {
  if (sdk.PETRUS_FAKE) return sdk.VERSION ?? sdk.version;
  let directory = path.dirname(fileURLToPath(moduleUrl));
  for (;;) {
    const manifest = path.join(directory, "package.json");
    try {
      const value = JSON.parse(fs.readFileSync(manifest, "utf8"));
      if (value.name === "@earendil-works/gondolin") return value.version;
    } catch (error) {
      if (error?.code !== "ENOENT") throw error;
    }
    const parent = path.dirname(directory);
    if (parent === directory) return undefined;
    directory = parent;
  }
}

const version = installedVersion();
if (version !== VERSION) throw new Error(`Gondolin SDK ${VERSION} required, found ${version ?? "unknown"}`);
const [nodeMajor, nodeMinor] = process.versions.node.split(".").map(Number);
if (!sdk.PETRUS_FAKE && (nodeMajor < 23 || (nodeMajor === 23 && nodeMinor < 6))) {
  throw new Error(`Gondolin requires Node >=23.6, found ${process.versions.node}`);
}
for (const name of ["VM", "RealFSProvider", "createHttpHooks", "resolveImageSelector", "loadGuestAssets"]) {
  if (typeof sdk[name] !== "function") throw new Error(`Gondolin public export ${name} is required`);
}
const { httpHooks } = sdk.createHttpHooks();
if (!httpHooks || typeof httpHooks !== "object") throw new Error("Gondolin createHttpHooks() returned no hooks");
let imageAssets;
try {
  const resolvedImage = sdk.resolveImageSelector(image);
  if (!resolvedImage || typeof resolvedImage.assetDir !== "string") throw new Error();
  imageAssets = sdk.loadGuestAssets(resolvedImage.assetDir);
} catch {
  throw new Error("Gondolin local image is unavailable");
}
const vm = await sdk.VM.create({
  sandbox: { vmm: "qemu", imagePath: imageAssets, netEnabled: true },
  vfs: { mounts: { "/petrus-transfer": new sdk.RealFSProvider(workspace) } },
  httpHooks,
});
let active = false;
let closing;
let server;
const connections = new Set();
let attachmentId;
const privateFiles = new Map();
const tombstones = new Map();
let privateUncertain = false;
let python;
let leaseTimer;
function armLeaseTimer(seconds = Number(ttlText)) {
  if (leaseTimer) clearTimeout(leaseTimer);
  leaseTimer = setTimeout(() => void close(), seconds * 1000);
  leaseTimer.unref();
}
const PY = String.raw`
import json
import os
import stat
import sys

R='/tmp/.petrus-private'
ROOT=R
LIMIT = 1024 * 1024
IDENTITY = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')

def valid_dir(value):
    return stat.S_ISDIR(value.st_mode) and stat.S_IMODE(value.st_mode) == 0o700 and value.st_uid == os.geteuid()

def valid_leaf(value):
    return stat.S_ISREG(value.st_mode) and stat.S_IMODE(value.st_mode) == 0o600 and value.st_uid == os.geteuid() and value.st_nlink == 1

def open_root(create=False):
    if create:
        try: os.mkdir(ROOT, 0o700)
        except FileExistsError: pass
    value = os.lstat(ROOT)
    if not valid_dir(value): raise OSError('root invariant')
    return os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)

def open_item(root_fd, item):
    value = os.stat(item, dir_fd=root_fd, follow_symlinks=False)
    if not valid_dir(value): raise OSError('item invariant')
    return os.open(item, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)

def absent(parent_fd, name):
    try: os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError: return True
    return False

def remove_at(parent_fd, name):
    try: value = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError: return True
    if stat.S_ISDIR(value.st_mode):
        try: child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
        except OSError: return False
        try:
            for entry in os.listdir(child):
                if not remove_at(child, entry): return False
        finally: os.close(child)
        try: os.rmdir(name, dir_fd=parent_fd)
        except OSError: return False
    else:
        try: os.unlink(name, dir_fd=parent_fd)
        except OSError: return False
    return absent(parent_fd, name)

def remove_root():
    temporary = os.open('/tmp', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try: return remove_at(temporary, '.petrus-private')
    finally: os.close(temporary)

def inspect_item(root_fd, item, expected_name):
    try: item_value = os.stat(item, dir_fd=root_fd, follow_symlinks=False)
    except FileNotFoundError: return False
    if not valid_dir(item_value): return False
    try: item_fd = os.open(item, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
    except OSError: return False
    try:
        names = os.listdir(item_fd)
        if names != [expected_name]: return False
        try: leaf = os.stat(expected_name, dir_fd=item_fd, follow_symlinks=False)
        except FileNotFoundError: return False
        return valid_leaf(leaf)
    finally: os.close(item_fd)

def cleanup_item(item, expected_name):
    try: root_value = os.lstat(ROOT)
    except FileNotFoundError: return 'unverified'
    if not valid_dir(root_value):
        remove_root()
        return 'unverified'
    root_fd = open_root()
    try:
        if absent(root_fd, item): return 'unverified'
        verified = inspect_item(root_fd, item, expected_name)
        removed = remove_at(root_fd, item)
        empty = not os.listdir(root_fd)
    finally: os.close(root_fd)
    if empty:
        try: os.rmdir(ROOT)
        except OSError: removed = False
    return 'clean' if verified and removed else 'unverified'

def cleanup_all(expected):
    try: root_value = os.lstat(ROOT)
    except FileNotFoundError:
        return ('not-created', 0) if not expected else ('unverified', 0)
    if not valid_dir(root_value):
        remove_root()
        return ('unverified', 0)
    root_fd = open_root()
    removed = 0
    try:
        names = os.listdir(root_fd)
        verified = set(names) == set(expected)
        for item in names:
            expected_name = expected.get(item)
            if expected_name is None or not inspect_item(root_fd, item, expected_name): verified = False
            if remove_at(root_fd, item) and expected_name is not None: removed += 1
            else: verified = False
        empty = not os.listdir(root_fd)
    finally: os.close(root_fd)
    if empty:
        try: os.rmdir(ROOT)
        except OSError: verified = False
    if os.path.lexists(ROOT): verified = False
    if not expected and verified: return ('not-created', 0)
    return ('clean', removed) if verified else ('unverified', removed)

def import_bytes(item, name, data):
    try:
        root_fd = open_root(create=True)
        try:
            if not absent(root_fd, item): raise OSError('item exists')
            os.mkdir(item, 0o700, dir_fd=root_fd)
            item_fd = open_item(root_fd, item)
            try:
                descriptor = os.open(name, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600, dir_fd=item_fd)
                try:
                    if len(data) > LIMIT: raise OSError('input bound')
                    view = memoryview(data)
                    while view:
                        written = os.write(descriptor, view)
                        if written <= 0: raise OSError('short write')
                        view = view[written:]
                    os.fsync(descriptor)
                    if not valid_leaf(os.fstat(descriptor)): raise OSError('leaf invariant')
                finally: os.close(descriptor)
            finally: os.close(item_fd)
        finally: os.close(root_fd)
    except BaseException:
        try:
            root_fd = open_root()
            try: remove_at(root_fd, item)
            finally: os.close(root_fd)
            if not os.listdir(ROOT): os.rmdir(ROOT)
        except OSError: pass
        raise

def import_file(item, name):
    data = sys.stdin.buffer.read(LIMIT + 1)
    if len(data) > LIMIT: raise OSError('input bound')
    import_bytes(item, name, data)

def export_bytes(item, name):
    root_fd = open_root()
    try:
        item_fd = open_item(root_fd, item)
        try:
            if os.listdir(item_fd) != [name]: raise OSError('unexpected leaf')
            descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=item_fd)
            try:
                before = os.fstat(descriptor)
                if not valid_leaf(before) or before.st_size > LIMIT: raise OSError('leaf invariant')
                chunks = []
                remaining = before.st_size
                while remaining:
                    chunk = os.read(descriptor, min(65536, remaining))
                    if not chunk: raise OSError('short read')
                    chunks.append(chunk)
                    remaining -= len(chunk)
                if os.read(descriptor, 1): raise OSError('long read')
                after = os.fstat(descriptor)
                if tuple(getattr(before, key) for key in IDENTITY) != tuple(getattr(after, key) for key in IDENTITY):
                    raise OSError('unstable leaf')
                return b''.join(chunks)
            finally: os.close(descriptor)
        finally: os.close(item_fd)
    finally: os.close(root_fd)

def export_file(item, name):
    sys.stdout.buffer.write(export_bytes(item, name))

def probe():
    item, name = '0123456789abcdef', 'leaf'
    if os.path.lexists(ROOT) and not remove_root(): raise OSError('probe cleanup failed')
    sample = b'private-probe'
    import_bytes(item, name, sample)
    if export_bytes(item, name) != sample: raise OSError('probe export failed')
    root_fd = open_root()
    item_fd = open_item(root_fd, item)
    victim = f'/tmp/.petrus-private-probe-victim-{os.getpid()}'
    try:
        try: os.open(name, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600, dir_fd=item_fd)
        except FileExistsError: pass
        else: raise OSError('exclusive create failed')
        victim_fd = os.open(victim, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        try: os.write(victim_fd, b'victim')
        finally: os.close(victim_fd)
        os.unlink(name, dir_fd=item_fd); os.symlink(victim, name, dir_fd=item_fd)
        try: export_bytes(item, name)
        except OSError: pass
        else: raise OSError('symlink export accepted')
        if open(victim, 'rb').read() != b'victim': raise OSError('victim touched')
        os.close(item_fd); item_fd = None
        os.close(root_fd); root_fd = None
        if cleanup_item(item, name) != 'unverified': raise OSError('symlink cleanup claimed clean')
        if open(victim, 'rb').read() != b'victim': raise OSError('victim touched')
    finally:
        if item_fd is not None: os.close(item_fd)
        if root_fd is not None: os.close(root_fd)
        try: os.unlink(victim)
        except FileNotFoundError: pass
        if os.path.lexists(ROOT): remove_root()
    if os.path.lexists(ROOT): raise OSError('root residue')
    sys.stdout.write('PRIVATE_PROBE_OK')

action = sys.argv[1]
if action == 'probe': probe()
elif action == 'import': import_file(sys.argv[2], sys.argv[3])
elif action == 'export': export_file(sys.argv[2], sys.argv[3])
elif action == 'delete': sys.stdout.write(cleanup_item(sys.argv[2], sys.argv[3]))
elif action == 'cleanup-all':
    expected = dict(json.loads(sys.stdin.buffer.read(LIMIT + 1)))
    disposition, removed = cleanup_all(expected)
    sys.stdout.write(json.dumps({'disposition': disposition, 'removed': removed}, separators=(',', ':')))
`;

async function close() {
  if (closing) return closing;
  closing = (async () => {
    let failed = false;
    try { await vm.close(); }
    catch { failed = true; }
    finally {
      if (failed) for (const connection of connections) connection.destroy();
      if (server) await new Promise((resolve) => server.close(resolve));
      fs.rmSync(socketPath, { force: true });
    }
    if (failed) {
      process.stderr.write("Gondolin VM close failed; terminating owned process group\n");
      setImmediate(() => {
        try { process.kill(-process.pid, "SIGKILL"); }
        catch { process.exit(1); }
      });
    }
  })();
  return closing;
}

function reply(connection, value) {
  return new Promise((resolve) => {
    if (connection.destroyed) { resolve(); return; }
    let settled = false;
    const done = () => {
      if (settled) return;
      settled = true;
      connection.off("close", done);
      resolve();
    };
    connection.once("close", done);
    connection.end(`${JSON.stringify(value)}\n`, done);
  });
}

function validRequest(request) {
  if (!request || typeof request !== "object" || !["handshake", "status", "attach", "export", "close", "execute", "private_probe", "private_import", "private_export", "private_delete", "private_cleanup"].includes(request.action)) return false;
  if (request.action !== "execute") return true;
  return Array.isArray(request.argv) && request.argv.length > 0 && request.argv.every((v) => typeof v === "string" && !v.includes("\0"))
    && typeof request.cwd === "string" && (request.cwd === "/workspace" || request.cwd.startsWith("/workspace/"))
    && request.environment && typeof request.environment === "object" && !Array.isArray(request.environment)
    && Object.entries(request.environment).every(([k, v]) => /^[A-Za-z_][A-Za-z0-9_]*$/.test(k) && typeof v === "string" && !v.includes("\0"))
    && Number.isSafeInteger(request.output_limit) && request.output_limit >= 0 && request.output_limit <= MAX_OUTPUT
    && (request.timeout === null || request.timeout === undefined || Number.isFinite(request.timeout) && request.timeout > 0);
}

const validAttachment = value => typeof value === "string" && value === value.trim() && value.length > 0 && Buffer.byteLength(value, "utf8") <= 128;
const validFileId = value => typeof value === "string" && /^[0-9a-f]{1,128}$/.test(value);
const validName = value => typeof value === "string" && /^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(value) && Buffer.byteLength(value, "ascii") <= 64;
function canonicalContent(value) {
  if (typeof value !== "string" || value.length > 1400000 || !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(value)) return undefined;
  const decoded = Buffer.from(value, "base64");
  return decoded.toString("base64") === value ? decoded : undefined;
}
function validPrivateRequest(request) {
  if (request.action === "private_probe") return true;
  if (!validAttachment(request.attachment_id)) return false;
  if (request.action === "private_cleanup") return true;
  if (!validFileId(request.file_id)) return false;
  if (request.action === "private_import") return validName(request.name) && canonicalContent(request.content) !== undefined;
  return validName(request.name);
}
function validPrivateRoots(request) {
  if (!validAttachment(request.attachment_id) || !request.private_roots || typeof request.private_roots !== "object" || Array.isArray(request.private_roots)) return false;
  const entries = Object.entries(request.private_roots);
  return entries.length <= 16 && entries.every(([name, reference]) => /^[A-Za-z_][A-Za-z0-9_]*$/.test(name)
    && reference && typeof reference === "object" && !Array.isArray(reference)
    && Object.keys(reference).sort().join() === "file_id,name"
    && validFileId(reference.file_id) && validName(reference.name));
}

async function helper(args, input) {
  const options = { stdout: "pipe", stderr: "pipe", windowBytes: 1024 * 1024 + 1 };
  if (input !== undefined) options.stdin = input;
  const proc = vm.exec([python, "-c", PY, ...args], options);
  const resultPromise = Promise.resolve(proc.result);
  resultPromise.catch(() => {});
  const chunks=[]; let stdoutSize=0; let stderrSize=0;
  for await (const {stream,data} of proc.output()) {
    const chunk = Buffer.from(data);
    if (stream === "stdout") { stdoutSize += chunk.length; if (stdoutSize <= 1024 * 1024) chunks.push(chunk); }
    else stderrSize += chunk.length;
    if (stdoutSize > 1024 * 1024 || stderrSize > 65536) { void close(); throw new Error("private operation failed"); }
  }
  const result=await resultPromise;
  if (result.exitCode !== 0) throw new Error("private operation failed");
  return Buffer.concat(chunks);
}

async function cleanupPrivateFiles() {
  if (!python) return { disposition: privateUncertain ? "unverified" : "not-created", removed: 0 };
  const expected = [...privateFiles].map(([id, value]) => [id, value.name]);
  let value;
  try {
    value = JSON.parse((await helper(["cleanup-all"], Buffer.from(JSON.stringify(expected)))).toString());
  } catch {
    privateUncertain = true;
    return { disposition: "unverified", removed: 0 };
  }
  const valid = value && ["clean", "not-created", "unverified"].includes(value.disposition)
    && Number.isSafeInteger(value.removed) && value.removed >= 0 && value.removed <= 16;
  if (!valid || value.disposition === "unverified" || privateUncertain) {
    privateUncertain = true;
    return { disposition: "unverified", removed: valid ? value.removed : 0 };
  }
  for (const [id, item] of privateFiles) tombstones.set(id, item.name);
  privateFiles.clear();
  return value;
}

async function privateAction(connection, request) {
  active=true;
  try {
    if (request.action === "private_probe") {
      if (python || attachmentId) throw new Error("private helper probe unavailable");
      armLeaseTimer(Math.max(Number(ttlText), 60));
      for (const candidate of ["/usr/bin/python3", "/bin/python3"]) try {
        python=candidate; const token=await helper(["probe"]); if (token.toString() !== "PRIVATE_PROBE_OK") throw new Error(); break;
      } catch { python=undefined; }
      if (!python) throw new Error("private helper probe failed");
      await reply(connection,{ok:true}); armLeaseTimer(); return;
    }
    if (!python || request.attachment_id !== attachmentId) throw new Error("private operation unavailable");
    if (request.action === "private_cleanup") {
      await reply(connection,{ok:true,...await cleanupPrivateFiles()}); return;
    }
    if (privateUncertain) throw new Error("private custody uncertain");
    if (request.action === "private_import") {
      const content=canonicalContent(request.content);
      if (privateFiles.size>=16 || content === undefined || privateFiles.has(request.file_id) || content.length>1024*1024) throw new Error("private import rejected");
      const total=[...privateFiles.values()].reduce((n,v)=>n+v.size,0); if(total+content.length>4*1024*1024) throw new Error("private import rejected");
      await helper(["import",request.file_id,request.name],content); privateFiles.set(request.file_id,{name:request.name,size:content.length}); tombstones.delete(request.file_id); await reply(connection,{ok:true}); return;
    }
    const item=privateFiles.get(request.file_id);
    if (!item) { if(request.action==="private_delete" && tombstones.get(request.file_id) === request.name) await reply(connection,{ok:true,disposition:"not-created",removed:0}); else throw new Error("private reference unavailable"); return; }
    if (item.name !== request.name) throw new Error("private reference unavailable");
    if(request.action==="private_export") { const content=await helper(["export",request.file_id,item.name]); await reply(connection,{ok:true,content:content.toString("base64")}); return; }
    const status=(await helper(["delete",request.file_id,item.name])).toString();
    if (status === "clean") { privateFiles.delete(request.file_id); tombstones.set(request.file_id, item.name); }
    else privateUncertain = true;
    await reply(connection,{ok:true,disposition:status,removed:status === "clean" ? 1 : 0});
  } catch {
    if (request.action === "private_import") privateUncertain = true;
    await reply(connection,{ok:false,error:"private operation failed"});
  } finally { active=false; }
}

async function runControl(argv) {
  const proc = vm.exec(argv, { stdout: "pipe", stderr: "pipe", windowBytes: 65536 });
  const resultPromise = Promise.resolve(proc.result);
  resultPromise.catch(() => {});
  let output = 0;
  for await (const { data } of proc.output()) {
    output += data.length;
    if (output > 65536) {
      void close();
      throw new Error("workspace transfer produced excessive output");
    }
  }
  const result = await resultPromise;
  if (result.exitCode !== 0) throw new Error("workspace transfer failed");
}

async function transferWorkspace(connection, action) {
  active = true;
  try {
    if (action === "attach") {
      const cleanup = await cleanupPrivateFiles();
      if(cleanup.disposition !== "clean" && cleanup.disposition !== "not-created") throw new Error("private attachment cleanup failed");
      tombstones.clear(); attachmentId = undefined;
      await runControl(["/bin/rm", "-rf", "/workspace"]);
      await runControl(["/bin/mkdir", "-p", "/workspace"]);
      await runControl(["/bin/tar", "-xf", "/petrus-transfer/input.tar", "-C", "/workspace"]);
      attachmentId = connection.petrusAttachment;
    } else {
      await runControl(["/bin/tar", "-cf", "/petrus-transfer/output.tar", "-C", "/workspace", "."]);
    }
    await reply(connection, { ok: true });
  } catch (error) {
    if (!closing) await reply(connection, { ok: false, error: String(error?.message ?? error) });
    else connection.destroy();
  } finally {
    active = false;
    if (closing) await closing;
  }
}

async function execute(connection, request) {
  active = true;
  let timedOut = false;
  let overflow = false;
  let ownedCancellation = false;
  let timer;
  const stdout = [];
  const stderr = [];
  let retained = 0;
  try {
    if (!validPrivateRoots(request)) throw new Error("invalid private roots");
    if (Object.keys(request.private_roots).length && request.attachment_id !== attachmentId) {
      throw new Error("attachment unavailable");
    }
    const env={...request.environment};
    for(const [name,reference] of Object.entries(request.private_roots??{})) {
      const item=privateFiles.get(reference.file_id);
      if(!item || item.name !== reference.name) throw new Error("private reference unavailable");
      env[name]=`/tmp/.petrus-private/${reference.file_id}`;
    }
    const proc = vm.exec(["/bin/sh", "-c", 'exec "$@"', "petrus-command", ...request.argv], {
      cwd: request.cwd,
      env,
      stdout: "pipe",
      stderr: "pipe",
      windowBytes: Math.max(65536, Math.min(MAX_FRAME, request.output_limit + 65536)),
    });
    const resultPromise = Promise.resolve(proc.result);
    // Observe rejection immediately, before cancellation can close the VM.
    resultPromise.catch(() => {});
    if (request.timeout != null) timer = setTimeout(() => {
      timedOut = true; ownedCancellation = true; void close();
    }, request.timeout * 1000);
    for await (const { stream, data } of proc.output()) {
      const chunk = Buffer.from(data);
      const available = Math.max(0, request.output_limit - retained);
      if (chunk.length > available) {
        overflow = true; ownedCancellation = true; void close();
      }
      if (available > 0) {
        const kept = chunk.subarray(0, available);
        (stream === "stdout" ? stdout : stderr).push(kept);
        retained += kept.length;
      }
    }
    const result = await resultPromise;
    await reply(connection, { ok: true, returncode: result.exitCode, stdout: Buffer.concat(stdout).toString("base64"),
      stderr: Buffer.concat(stderr).toString("base64"), timed_out: timedOut, output_truncated: overflow });
  } catch (error) {
    if (ownedCancellation) await reply(connection, { ok: true, returncode: -15, stdout: Buffer.concat(stdout).toString("base64"),
      stderr: Buffer.concat(stderr).toString("base64"), timed_out: timedOut, output_truncated: overflow });
    else if (!closing) await reply(connection, { ok: false, error: String(error?.message ?? error) });
    else connection.destroy();
  } finally {
    if (timer) clearTimeout(timer);
    active = false;
    if (closing) await closing;
  }
}

server = net.createServer((connection) => {
  connections.add(connection);
  connection.on("close", () => connections.delete(connection));
  connection.on("error", () => {});
  let data = Buffer.alloc(0);
  connection.on("data", (chunk) => {
    if (data === null) return;
    data = Buffer.concat([data, chunk]);
    if (data.length > MAX_FRAME) { data = null; void reply(connection, { ok: false, error: "request too large" }); return; }
    const newline = data.indexOf(10);
    if (newline < 0) return;
    let request;
    try { request = JSON.parse(data.subarray(0, newline).toString("utf8")); }
    catch { data = null; void reply(connection, { ok: false, error: "invalid request" }); return; }
    data = null;
    if (!validRequest(request)) { void reply(connection, { ok: false, error: "invalid request" }); return; }
    if (request.lease_id !== leaseId || request.boot_token !== bootToken) { void reply(connection, { ok: false, error: "authentication failed" }); return; }
    if (request.action === "handshake" || request.action === "status") {
      void reply(connection, { ok: true, lease_id: leaseId, version, runtime: process.version, active, closing: Boolean(closing) }); return;
    }
    if (request.action === "close") { void (async () => { await reply(connection, { ok: true }); await close(); })(); return; }
    if (active) { void reply(connection, { ok: false, error: "command already active" }); return; }
    if (request.action === "attach" || request.action === "export") {
      if (request.action === "attach" && !validAttachment(request.attachment_id)) { void reply(connection, { ok: false, error: "invalid transfer request" }); return; }
      connection.petrusAttachment=request.attachment_id; void transferWorkspace(connection, request.action); return;
    }
    if (request.action.startsWith("private_")) {
      if (!validPrivateRequest(request)) { void reply(connection, { ok: false, error: "invalid private request" }); return; }
      void privateAction(connection, request); return;
    }
    void execute(connection, request);
  });
});

fs.rmSync(socketPath, { force: true });
server.listen(socketPath, () => fs.chmodSync(socketPath, 0o600));
armLeaseTimer(startupMode === "private" ? Math.max(Number(ttlText), 60) : Number(ttlText));
for (const name of ["SIGTERM", "SIGINT"]) process.on(name, () => void close());
process.on("exit", () => fs.rmSync(socketPath, { force: true }));
