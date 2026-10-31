// Pins the scopes the amk injections give engine programs, over the makefile, lua, python, and javascript grammars the editor ships.
const fs = require('fs');
const path = require('path');
const vsctm = require('vscode-textmate');
const oniguruma = require('vscode-oniguruma');
const { enginesGrammar, expansionsGrammar } = require('../build.js');

const BUILTIN = process.env.VSCODE_EXTENSIONS || '/Applications/Visual Studio Code.app/Contents/Resources/app/extensions';
const SHIPPED = {
  'source.makefile': 'make/syntaxes/make.tmLanguage.json',
  'source.lua': 'lua/syntaxes/lua.tmLanguage.json',
  'source.python': 'python/syntaxes/MagicPython.tmLanguage.json',
  'source.js': 'javascript/syntaxes/JavaScript.tmLanguage.json',
  'source.shell': 'shellscript/syntaxes/shell-unix-bash.tmLanguage.json',
  'source.go': 'go/syntaxes/go.tmLanguage.json',
};
const STUBS = {
  'source.scheme': { scopeName: 'source.scheme', patterns: [{ name: 'keyword.control.scheme', match: '\\b(define|let|if|lambda)\\b' }] },
  'source.zig': { scopeName: 'source.zig', patterns: [{ name: 'keyword.control.zig', match: '\\b(fn|pub|export|return)\\b' }] },
  'source.wat': { scopeName: 'source.wat', patterns: [{ name: 'keyword.control.wat', match: '\\b(module|func|export|param|result)\\b' }] },
  'source.makefile.amk-engines': enginesGrammar(),
  'source.makefile.amk-expansions': expansionsGrammar(),
};

const onigLib = oniguruma
  .loadWASM(fs.readFileSync(require.resolve('vscode-oniguruma/release/onig.wasm')).buffer)
  .then(() => ({
    createOnigScanner: (patterns) => new oniguruma.OnigScanner(patterns),
    createOnigString: (s) => new oniguruma.OnigString(s),
  }));

const registry = new vsctm.Registry({
  onigLib,
  loadGrammar: async (scope) => {
    if (STUBS[scope]) return vsctm.parseRawGrammar(JSON.stringify(STUBS[scope]), `${scope}.json`);
    if (SHIPPED[scope]) {
      const file = path.join(BUILTIN, SHIPPED[scope]);
      return vsctm.parseRawGrammar(fs.readFileSync(file, 'utf8'), file);
    }
    return null;
  },
  getInjections: (scope) =>
    scope === 'source.makefile' ? ['source.makefile.amk-engines', 'source.makefile.amk-expansions'] : undefined,
});

// A case tokenizes its lines as one file and checks the token holding find on line; a scope ending in a dot is a prefix.
const CASES = [
  // the at line itself
  { name: 'at sign', lines: ['@lua.import', 'define fns', 'endef'], line: 0, find: '@', scope: 'punctuation.definition.decorator.amk' },
  { name: 'engine word', lines: ['@lua.import', 'define fns', 'endef'], line: 0, find: 'lua', scope: 'entity.name.function.decorator.engine.amk' },
  { name: 'define name', lines: ['@lua.import', 'define fns', 'endef'], line: 1, find: 'fns', scope: 'variable.other.makefile' },
  { name: 'endef keyword', lines: ['@lua.import', 'define fns', 'endef'], line: 2, find: 'endef', scope: 'keyword.control.define.makefile' },

  // each engine body takes its language
  { name: 'lua body', lines: ['@lua.import', 'define fns', '  function f() end', 'endef'], line: 2, find: 'function', scope: 'meta.embedded.block.lua' },
  { name: 'lua keyword', lines: ['@lua.import', 'define fns', '  function f() end', 'endef'], line: 2, find: 'function', scope: 'keyword.' },
  { name: 'python body', lines: ['@micropy.exec', 'define side', '  def f(n): return n', 'endef'], line: 2, find: 'def', scope: 'storage.type.function.python' },
  { name: 'js body', lines: ['@js.import.target', 'define report', '  function shout(s) {}', 'endef'], line: 2, find: 'function', scope: 'meta.embedded.block.javascript' },
  { name: 's7 body', lines: ['@s7.import', 'define myfact', '  (define (fact n) n)', 'endef'], line: 2, find: 'define', scope: 'keyword.control.scheme' },
  { name: 'go body', lines: ['@tinygo.import', 'define fib.go', '  package main', '  func fib(n int) int { return n }', 'endef'], line: 3, find: 'func', scope: 'meta.embedded.block.go' },
  { name: 'go keyword', lines: ['@tinygo.import', 'define fib.go', '  package main', '  func fib(n int) int { return n }', 'endef'], line: 3, find: 'func', scope: 'keyword.function.go' },
  { name: 'zig body', lines: ['@zig.import', 'define fib.zig', '  export fn fib(n: u32) u32 { return n; }', 'endef'], line: 2, find: 'fn', scope: 'keyword.control.zig' },
  { name: 'wat body', lines: ['@wat.import', 'define fib.wat', '  (module (func $fib (export "fib")))', 'endef'], line: 2, find: 'module', scope: 'keyword.control.wat' },

  // blank and comment lines may stand between the at line and its define
  { name: 'gap', lines: ['@lua.import', '', '# lua helpers', 'define fns', '  return 1', 'endef'], line: 4, find: 'return', scope: 'meta.embedded.block.lua' },
  { name: 'gap comment', lines: ['@lua.import', '# lua helpers', 'define fns', 'endef'], line: 1, find: 'lua helpers', scope: 'comment.line.number-sign.makefile' },
  { name: 'override define', lines: ['@lua.import', 'override define fns', '  return 1', 'endef'], line: 2, find: 'return', scope: 'meta.embedded.block.lua' },

  // the block ends at endef, whatever state the guest grammar is in
  { name: 'after endef', lines: ['@lua.import', 'define fns', '  return 1', 'endef', 'x := 1'], line: 4, find: 'x', scope: 'meta.engine.', absent: true },
  { name: 'unclosed string', lines: ['@micropy.import', 'define doc', '  s = """open', 'endef', 'y := 2'], line: 4, find: 'y', scope: 'string.', absent: true },
  { name: 'next block', lines: ['@lua.import', 'define a', 'endef', '@js.import', 'define b', '  let x = 1', 'endef'], line: 5, find: 'let', scope: 'meta.embedded.block.javascript' },

  // only an at line names a language, and a stray line ends the block
  { name: 'no at line', lines: ['define lua.side', '  function f() end', 'endef'], line: 1, find: 'function', scope: 'meta.embedded.', absent: true },
  { name: 'stray line', lines: ['@lua.import', 'x := 1', 'define fns', '  return 1', 'endef'], line: 3, find: 'return', scope: 'meta.embedded.', absent: true },
  { name: 'unknown engine', lines: ['@cobol.import', 'define fns', '  return 1', 'endef'], line: 2, find: 'return', scope: 'meta.embedded.', absent: true },

  // make and goal references inside a body, strings included
  { name: 'make ref in string', lines: ['@lua.exec', 'define side', '  local f = amk.expand("$(factors " .. n .. ")")', 'endef'], line: 2, find: 'factors', scope: 'variable.other.amk' },
  { name: 'make ref keeps string', lines: ['@lua.exec', 'define side', '  local f = amk.expand("$(factors " .. n .. ")")', 'endef'], line: 2, find: 'factors', scope: 'string.' },
  { name: 'goal ref', lines: ['@lua.import.target', 'define sorted', '  for x in (">>nums.txt<<"):gmatch("%S+") do end', 'endef'], line: 2, find: 'nums.txt', scope: 'variable.other.goal.amk' },
  { name: 'python decorator', lines: ['@micropy.import', 'define server', '  @app.post("/")', 'endef'], line: 2, find: 'app', scope: 'variable.other.goal.amk', absent: true },

  // the decorator grammar: options in braces, a positional group, quoted literals, prerequisites, the mark
  { name: 'option key', lines: ['@ops.bind.js{kind=scoped restart=never}', 'define f', 'endef'], line: 0, find: 'kind', scope: 'variable.parameter.key.amk' },
  { name: 'option braces', lines: ['@ops.bind.js{kind=scoped}', 'define f', 'endef'], line: 0, find: '{', scope: 'punctuation.section.braces.begin.amk' },
  { name: 'bind body', lines: ['@ops.bind.js{kind=goal}', 'define f', '  function g() {}', 'endef'], line: 2, find: 'function', scope: 'meta.embedded.block.javascript' },
  { name: 'tuple group', lines: ['@shop.bind.lua (order item=str "big order")', 'define price', 'endef'], line: 0, find: '(', scope: 'punctuation.section.group.begin.amk' },
  { name: 'tuple field key', lines: ['@shop.bind.lua (order item=str "big order")', 'define price', 'endef'], line: 0, find: 'item', scope: 'variable.parameter.key.amk' },
  { name: 'quoted literal', lines: ['@shop.bind.lua (order item=str "big order")', 'define price', 'endef'], line: 0, find: 'big order', scope: 'string.quoted.double.amk' },
  { name: 'tuple body', lines: ['@shop.bind.lua (order item=str)', 'define price', '  local x = 1', 'endef'], line: 2, find: 'local', scope: 'meta.embedded.block.lua' },
  { name: 'prerequisite', lines: ['@amk.target{join=;} : first second', 'define report', '  echo hi', 'endef'], line: 0, find: 'second', scope: 'entity.name.function.target.makefile' },
  { name: 'shell body', lines: ['@amk.target : first', 'define report', '  echo hi', 'endef'], line: 2, find: 'echo', scope: 'meta.embedded.block.shellscript' },
  { name: 'space target body', lines: ['@shop.amk: orders', 'define report', '  shop.all', 'endef'], line: 2, find: 'shop.all', scope: 'meta.embedded.block.shellscript' },
  { name: 'bash body', lines: ['@bash.target', 'define hello', '  echo hi', 'endef'], line: 2, find: 'echo', scope: 'meta.embedded.block.shellscript' },
  { name: 'fxn body is make', lines: ['@amk.fxn', 'define log', '$(info log: $(2))', 'endef'], line: 2, find: 'info', scope: 'meta.embedded.', absent: true },
  { name: 'mark', lines: ['@lua.import ::: postfix', 'define d', 'endef'], line: 0, find: 'postfix', scope: 'keyword.other.mark.amk' },
  { name: 'plain decorator', lines: ['@troupe', 'define ops', '{}', 'endef'], line: 0, find: 'troupe', scope: 'entity.name.function.decorator.amk' },
  { name: 'plain decorator deps', lines: ['@probe --flag : dep', 'define d', 'endef'], line: 0, find: 'dep', scope: 'entity.name.function.target.makefile' },
  { name: 'assignment is not a decorator', lines: ['@name := 1'], line: 0, find: 'name', scope: 'entity.name.function.decorator.amk', absent: true },
];

function scopesAt(tokens, text, find) {
  const at = text.indexOf(find);
  if (at < 0) throw new Error(`"${find}" is not in "${text}"`);
  return tokens.find((t) => t.startIndex <= at && at < t.endIndex).scopes;
}

function carries(scopes, want) {
  return scopes.some((s) => (want.endsWith('.') ? s.startsWith(want) : s === want));
}

(async () => {
  const grammar = await registry.loadGrammar('source.makefile');
  let failed = 0;
  for (const c of CASES) {
    let state = vsctm.INITIAL;
    let scopes;
    c.lines.forEach((text, i) => {
      const r = grammar.tokenizeLine(text, state);
      if (i === c.line) scopes = scopesAt(r.tokens, text, c.find);
      state = r.ruleStack;
    });
    const ok = carries(scopes, c.scope) !== Boolean(c.absent);
    if (!ok) failed++;
    console.log(`${ok ? 'ok  ' : 'FAIL'} ${c.name}: "${c.find}" ${c.absent ? 'lacks' : 'has'} ${c.scope}${ok ? '' : `\n     got ${scopes.join(' ')}`}`);
  }
  console.log(`${CASES.length - failed}/${CASES.length} passed`);
  process.exit(failed ? 1 : 0);
})();
