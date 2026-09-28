// Small display-only highlighter for JSON and the Bash commands we generate.
// Reuse the Docs token styles; all input is inserted as text, never as HTML.
const JSON_TOKEN = /"(?:\\.|[^"\\])*"|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|\b(?:true|false|null)\b/g;
const SHELL_TOKEN = /'[^']*'|"(?:\\.|[^"\\])*"|\\[\s\S]|--?[A-Za-z][A-Za-z-]*|\$[A-Za-z_][A-Za-z0-9_]*|\b(?:curl|read|printf|unset|GET|POST|PATCH|PUT|DELETE|HEAD|OPTIONS)\b/g;

export function highlightCode(element, text, language) {
  const pattern = language === 'json' ? JSON_TOKEN : SHELL_TOKEN;
  const fragment = document.createDocumentFragment();
  let offset = 0;
  for (const match of text.matchAll(pattern)) {
    const token = match[0];
    fragment.append(document.createTextNode(text.slice(offset, match.index)));
    let kind;
    if (language === 'json') {
      kind = token.startsWith('"')
        ? (/^\s*:/.test(text.slice(match.index + token.length)) ? 'key' : 'string')
        : (/^-?\d/.test(token) ? 'number' : 'literal');
    } else if (token.startsWith("'") || token.startsWith('"')) {
      kind = 'string';
    } else if (token.startsWith('-')) {
      kind = 'flag';
    } else if (token.startsWith('$')) {
      kind = 'placeholder';
    } else if (/^(curl|read|printf|unset)$/.test(token)) {
      kind = 'command';
    } else if (/^[A-Z]+$/.test(token)) {
      kind = 'method';
    }
    if (kind) {
      const span = document.createElement('span');
      span.className = 'tok-' + kind;
      span.textContent = token;
      fragment.append(span);
    } else {
      fragment.append(document.createTextNode(token));
    }
    offset = match.index + token.length;
  }
  fragment.append(document.createTextNode(text.slice(offset)));
  element.replaceChildren(fragment);
}
