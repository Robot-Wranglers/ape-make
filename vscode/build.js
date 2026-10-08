// Generates the amk injection grammars and stages them as an unpacked vsix: node build.js <dir>.
const fs = require('fs');
const path = require('path');

// The engine an at line names, and the grammar its define body takes.
const ENGINES = {
  lua: { scope: 'source.lua', lang: 'lua' },
  micropy: { scope: 'source.python', lang: 'python' },
  js: { scope: 'source.js', lang: 'javascript' },
  s7: { scope: 'source.scheme', lang: 'scheme' },
  jq: { scope: 'source.jq', lang: 'jq' },
  awk: { scope: 'source.awk', lang: 'awk' },
};

const MODIFIERS = '(?:(?:override|export|private)\\s+)*';
const DEFINE = `^\\s*(${MODIFIERS})(define)\\s+(\\S+)(?:\\s*(=|\\?=|:=|::=|\\+=|!=))?(.*)$`;
const ENDEF = '^\\s*(endef)\\b';

// Between the at line and its define only blank and comment lines may stand; anything else ends the block.
const STRAY = `^(?!\\s*(?:#|$)|\\s*${MODIFIERS}define\\b)`;

function engineBlock(name, { scope, lang }) {
  return {
    name: `meta.engine.${name}.amk`,
    begin: `^(@)(${name})((?:\\.[\\w-]+)*\\*?)(?=\\s|$)(.*)$`,
    beginCaptures: {
      1: { name: 'punctuation.definition.decorator.amk' },
      2: { name: 'entity.name.function.decorator.engine.amk' },
      3: { name: 'entity.name.function.decorator.amk' },
      4: { name: 'meta.arguments.decorator.amk' },
    },
    end: `${ENDEF}|${STRAY}`,
    endCaptures: { 1: { name: 'keyword.control.define.makefile' } },
    patterns: [
      { match: '^\\s*(#.*)$', captures: { 1: { name: 'comment.line.number-sign.makefile' } } },
      {
        begin: DEFINE,
        beginCaptures: {
          1: { name: 'keyword.control.override.makefile' },
          2: { name: 'keyword.control.define.makefile' },
          3: { name: 'variable.other.makefile' },
          4: { name: 'punctuation.separator.key-value.makefile' },
        },
        while: '^(?!\\s*endef\\b)',
        contentName: `meta.embedded.block.${lang}`,
        patterns: [{ include: scope }],
      },
    ],
  };
}

function enginesGrammar() {
  const repository = {};
  for (const [name, engine] of Object.entries(ENGINES)) repository[`engine-${name}`] = engineBlock(name, engine);
  return {
    scopeName: 'source.makefile.amk-engines',
    injectionSelector: 'L:source.makefile -comment -meta.embedded',
    patterns: Object.keys(repository).map((key) => ({ include: `#${key}` })),
    repository,
  };
}

// Make references and goal references inside an engine body, strings included, since the body reaches the engine unexpanded.
function expansionsGrammar() {
  return {
    scopeName: 'source.makefile.amk-expansions',
    injectionSelector: 'L:meta.embedded.block -comment',
    patterns: [
      {
        match: '(\\$[({])([\\w.*?+-]+)',
        captures: {
          1: { name: 'punctuation.definition.variable.amk' },
          2: { name: 'variable.other.amk' },
        },
      },
      {
        match: '(@)([\\w.-][\\w./-]*)(@)',
        captures: {
          1: { name: 'punctuation.definition.goal.amk' },
          2: { name: 'variable.other.goal.amk' },
          3: { name: 'punctuation.definition.goal.amk' },
        },
      },
    ],
  };
}

function vsixManifest(pkg) {
  return `<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011">
  <Metadata>
    <Identity Language="en-US" Id="${pkg.name}" Version="${pkg.version}" Publisher="${pkg.publisher}" />
    <DisplayName>${pkg.displayName}</DisplayName>
    <Description xml:space="preserve">${pkg.description}</Description>
    <Categories>${pkg.categories.join(',')}</Categories>
    <Properties>
      <Property Id="Microsoft.VisualStudio.Code.Engine" Value="${pkg.engines.vscode}" />
    </Properties>
  </Metadata>
  <Installation>
    <InstallationTarget Id="Microsoft.VisualStudio.Code" />
  </Installation>
  <Dependencies />
  <Assets>
    <Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true" />
  </Assets>
</PackageManifest>
`;
}

const CONTENT_TYPES = `<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension=".json" ContentType="application/json" />
  <Default Extension=".vsixmanifest" ContentType="text/xml" />
</Types>
`;

function stage(dir) {
  const pkg = JSON.parse(fs.readFileSync(path.join(__dirname, 'package.json'), 'utf8'));
  const { scripts, devDependencies, ...shipped } = pkg;
  const ext = path.join(dir, 'extension');
  fs.mkdirSync(path.join(ext, 'syntaxes'), { recursive: true });
  const write = (rel, text) => fs.writeFileSync(path.join(dir, rel), text);
  write('extension/package.json', JSON.stringify(shipped, null, 2) + '\n');
  write('extension/syntaxes/amk-engines.injection.json', JSON.stringify(enginesGrammar(), null, 2) + '\n');
  write('extension/syntaxes/amk-expansions.injection.json', JSON.stringify(expansionsGrammar(), null, 2) + '\n');
  write('extension.vsixmanifest', vsixManifest(pkg));
  write('[Content_Types].xml', CONTENT_TYPES);
}

module.exports = { ENGINES, enginesGrammar, expansionsGrammar };

if (require.main === module) {
  if (!process.argv[2]) {
    console.error('usage: node build.js <dir>');
    process.exit(2);
  }
  stage(process.argv[2]);
}
