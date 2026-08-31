'use strict';

// Unit tests for bin/cli.js — verb parsing, flag parsing, browser-open
// suppression, and the off-platform subcommand messages. These deliberately
// never bootstrap dependencies or launch servers: they only call the exported
// parsing/dispatch helpers.

const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const cli = require('./cli.js');

// Run fn with console.error / console.log captured so tests can assert on what
// a subcommand prints without any of it reaching the test output.
function captured(fn) {
  const origError = console.error;
  const origLog = console.log;
  const errLines = [];
  const logLines = [];
  console.error = (...a) => errLines.push(a.map(String).join(' '));
  console.log = (...a) => logLines.push(a.map(String).join(' '));
  try {
    return { result: fn(), errLines, logLines };
  } finally {
    console.error = origError;
    console.log = origLog;
  }
}

test('the bare invocation means dashboard', () => {
  assert.deepStrictEqual(cli.parseInvocation([]), { verb: 'dashboard', args: [] });
});

test('a known verb is recognized and stripped from the args', () => {
  for (const verb of cli.VERBS) {
    assert.deepStrictEqual(cli.parseInvocation([verb]), { verb, args: [] });
  }
  assert.deepStrictEqual(cli.parseInvocation(['dashboard', '--no-open']), {
    verb: 'dashboard',
    args: ['--no-open'],
  });
  assert.deepStrictEqual(cli.parseInvocation(['status', '--port', '4000']), {
    verb: 'status',
    args: ['--port', '4000'],
  });
});

test('a first arg that is not a known verb falls through to dashboard', () => {
  // Existing flags keep working bare, and a stray argument cannot silently
  // change what the command does.
  assert.deepStrictEqual(cli.parseInvocation(['--port', '4000']), {
    verb: 'dashboard',
    args: ['--port', '4000'],
  });
  assert.deepStrictEqual(cli.parseInvocation(['--bogus']), {
    verb: 'dashboard',
    args: ['--bogus'],
  });
});

test('unknown flags still error during dashboard flag parsing', () => {
  assert.throws(() => cli.parseArgs(['--bogus']), cli.UsageError);
  assert.throws(() => cli.parseArgs(['--bogus']), /unknown argument: --bogus/);
});

test('parseArgs keeps every default option', () => {
  const { help, options } = cli.parseArgs([]);
  assert.strictEqual(help, false);
  assert.strictEqual(options.frontPort, 3000);
  assert.strictEqual(options.apiPort, 8000);
  assert.strictEqual(options.host, '127.0.0.1');
  assert.strictEqual(options.allowedOrigins, '');
  assert.strictEqual(options.authToken, '');
  assert.strictEqual(options.insecureNoAuth, false);
  assert.strictEqual(options.dataDir, null);
  assert.strictEqual(options.noOpen, false);
});

test('--no-open parses to noOpen and survives alongside other flags', () => {
  assert.strictEqual(cli.parseArgs(['--no-open']).options.noOpen, true);
  const { options } = cli.parseArgs(['--no-open', '--port', '4000']);
  assert.strictEqual(options.noOpen, true);
  assert.strictEqual(options.frontPort, 4000);
});

test('--no-open suppresses the browser launch', () => {
  assert.strictEqual(cli.shouldOpenBrowser({ noOpen: true }), false);
  assert.strictEqual(cli.shouldOpenBrowser({ noOpen: false }), true);
});

test('AGENT_HARNESS_NO_OPEN still suppresses the browser launch', () => {
  const prev = process.env.AGENT_HARNESS_NO_OPEN;
  try {
    delete process.env.AGENT_HARNESS_NO_OPEN;
    assert.strictEqual(cli.shouldOpenBrowser({ noOpen: false }), true);
    process.env.AGENT_HARNESS_NO_OPEN = '1';
    assert.strictEqual(cli.shouldOpenBrowser({ noOpen: false }), false);
    assert.strictEqual(cli.shouldOpenBrowser({ noOpen: true }), false);
  } finally {
    if (prev === undefined) delete process.env.AGENT_HARNESS_NO_OPEN;
    else process.env.AGENT_HARNESS_NO_OPEN = prev;
  }
});

test('menubar is macOS-only off macOS and never mentions rumps', () => {
  assert.strictEqual(
    cli.menubarMessage('linux'),
    'The tokentelemetry menu bar is macOS-only.',
  );
  assert.strictEqual(
    cli.menubarMessage('win32'),
    'The tokentelemetry menu bar is macOS-only.',
  );
  assert.strictEqual(
    cli.menubarMessage('darwin'),
    'The tokentelemetry menu bar is not implemented yet.',
  );
});

test('desktop reports not available on every platform', () => {
  assert.strictEqual(
    cli.desktopMessage(),
    'The tokentelemetry desktop app is not available yet.',
  );
});

test('status and stop report not-available-yet', () => {
  assert.strictEqual(cli.statusMessage(), 'tokentelemetry status is not implemented yet.');
  assert.strictEqual(cli.stopMessage(), 'tokentelemetry stop is not implemented yet.');
});

test('subcommand handlers print one line and exit non-zero', () => {
  for (const fn of [cli.cmdMenubar, cli.cmdDesktop, cli.cmdStatus, cli.cmdStop]) {
    const { result, errLines } = captured(fn);
    assert.strictEqual(result, 1);
    assert.strictEqual(errLines.length, 1);
  }
});

test('main dispatches subcommands without bootstrapping or launching servers', async () => {
  const status = captured(() => cli.main(['status']));
  assert.strictEqual(await status.result, 1);
  assert.strictEqual(status.errLines[0], 'tokentelemetry status is not implemented yet.');

  const stop = captured(() => cli.main(['stop']));
  assert.strictEqual(await stop.result, 1);
  assert.strictEqual(stop.errLines[0], 'tokentelemetry stop is not implemented yet.');

  const desktop = captured(() => cli.main(['desktop']));
  assert.strictEqual(await desktop.result, 1);
  assert.strictEqual(desktop.errLines[0], 'The tokentelemetry desktop app is not available yet.');

  const menubar = captured(() => cli.main(['menubar']));
  assert.strictEqual(await menubar.result, 1);
  assert.strictEqual(menubar.errLines.length, 1);
  assert.strictEqual(menubar.errLines[0], cli.menubarMessage(process.platform));
});

test('main --help prints usage and exits 0', async () => {
  const help = captured(() => cli.main(['--help']));
  assert.strictEqual(await help.result, 0);
  const text = help.logLines.join('\n');
  assert.ok(text.includes('Usage: tokentelemetry'));
  assert.ok(text.includes('dashboard'));
  assert.ok(text.includes('--no-open'));
});

test('path-hint is not a recognized verb', () => {
  // The installer used to reach a hidden path-hint subcommand; it is gone, so
  // `tokentelemetry path-hint` must fall through to dashboard flag parsing and
  // fail as an unknown argument instead of printing installer guidance.
  assert.ok(!cli.VERBS.includes('path-hint'));
  assert.deepStrictEqual(cli.parseInvocation(['path-hint']), {
    verb: 'dashboard',
    args: ['path-hint'],
  });
  assert.throws(() => cli.parseArgs(['path-hint']), cli.UsageError);
  assert.throws(() => cli.parseArgs(['path-hint']), /unknown argument: path-hint/);
});

test('install.sh selects the rc file locally instead of calling path-hint', () => {
  const script = fs.readFileSync(path.join(__dirname, '..', 'install.sh'), 'utf8');
  assert.ok(!script.includes('path-hint'), 'install.sh must not reach a CLI subcommand for PATH guidance');
  assert.ok(script.includes('*/zsh'), 'install.sh should branch on zsh to ~/.zshrc');
  assert.ok(script.includes('*/bash'), 'install.sh should branch on bash to ~/.bashrc');
  assert.ok(script.includes('~/.zshrc') && script.includes('~/.bashrc'),
    'install.sh should still tell the user which rc file to edit');
});