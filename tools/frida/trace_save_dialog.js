// Ravenswatch save dialog trace — Frida script.
//
// Hooks the chapter-end save-or-continue modal path and save job APIs.
// Drive from WSL with a UNC -l path so edits do not need copying:
//   printf 'ready()\n' | frida.exe -n Ravenswatch.exe -l '\\wsl.localhost\...\tools\frida\trace_save_dialog.js'

'use strict';

const MODULE_NAME = 'Ravenswatch.exe';

const HOOKS = [
    ['modal_open_save_or_quit', 0x27fde0],
    ['game_end_success',       0x282df0],
    ['game_end_skip_next',     0x282b50],
    ['save_dialog_network_evt',0x2832c0],
    ['session_end_result',     0x28f140],
    ['session_end_apply',      0x28f660],
    ['post_save_saved_state',  0x291350],
    ['post_abandon_state',     0x291190],
    ['save_request_async',     0x679760],
    ['save_request_sync',      0x6797b0],
];

// This callback is intentionally opt-in. It fires continuously with an event
// code of 2 during normal modal lifetime, and its arg0 is not the session.
const HOT_HOOKS = [
    ['modal_callback',         0x281b40],
];

let MOD = null;

function info(m) { console.log('[+] ' + m); }
function warn(m) { console.log('[!] ' + m); }

function safeU32(p) {
    try { return p.readU32(); } catch (_) { return null; }
}

function safeU8(p) {
    try { return p.readU8(); } catch (_) { return null; }
}

function safePtr(p) {
    try { return p.readPointer(); } catch (_) { return NULL; }
}

function jobSummary(job) {
    if (!job || job.isNull()) return 'job=NULL';
    const data = safePtr(job.add(0x30));
    const size = safeU32(job.add(0x38));
    const pend = safeU32(job.add(0x7c));
    const done = safeU32(job.add(0x80));
    const result = safeU8(job.add(0x84));
    return 'job=' + job + ' data=' + data + ' size=' + size +
           ' pend=' + pend + ' done=' + done + ' result=' + result;
}

function sessionSummary(session) {
    if (!session || session.isNull()) return 'session=NULL';
    return 'session=' + session +
           ' state=' + safeU32(session.add(0x150)) +
           ' saved=' + safeU8(session.add(0x30)) +
           ' first=' + safeU8(session.add(0x159)) +
           ' a5=' + safeU8(session.add(0xa5)) +
           ' modal=' + safePtr(session.add(0xf8));
}

function installHook(name, rva) {
    const addr = MOD.base.add(rva);
    Interceptor.attach(addr, {
        onEnter(args) {
            this.name = name;
            this.t0 = Date.now();
            let line = name + ' @ ' + addr + ' ';

            if (name === 'save_request_async' || name === 'save_request_sync') {
                line += 'manager=' + args[0] + ' ' + jobSummary(args[1]);
            } else if (name === 'modal_callback') {
                line += 'arg0=' + args[0] + ' event_code=' + args[1].toInt32() +
                        ' arg2=' + args[2] + ' arg3=' + args[3];
            } else if (name === 'session_end_result' || name === 'session_end_apply') {
                const result = safeU32(args[1].add(0x60));
                line += sessionSummary(args[0]) + ' result_record=' + args[1] +
                        ' result_code=' + result;
            } else {
                line += sessionSummary(args[0]);
            }
            info(line);
        },
        onLeave(retval) {
            if (this.name === 'save_request_async') {
                info(this.name + ' returned seq=' + retval.toInt32() +
                     ' (' + (Date.now() - this.t0) + 'ms)');
            } else if (this.name === 'save_request_sync') {
                info(this.name + ' returned (' + (Date.now() - this.t0) + 'ms)');
            }
        }
    });
}

function main() {
    MOD = Process.findModuleByName(MODULE_NAME);
    if (!MOD) {
        warn(MODULE_NAME + ' not loaded');
        return;
    }
    info('image_base=' + MOD.base);
    for (const h of HOOKS) installHook(h[0], h[1]);
    info('trace hooks installed; now use the in-game save-or-continue dialog');
}

globalThis.ready = function() {
    info('trace is already active');
};

globalThis.hot = function() {
    for (const h of HOT_HOOKS) installHook(h[0], h[1]);
    info('hot hooks installed');
};

main();
