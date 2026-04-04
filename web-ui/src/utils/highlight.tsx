/**
 * Render tokens from tree-sitter parser into highlighted React nodes.
 * Also provides a regex fallback for when parser isn't ready.
 */

import type { Token, TokenType } from "./cParser";

const TYPE_CSS: Record<TokenType, string> = {
  keyword: "hl-kw",
  type: "hl-kw",       // types use same color as keywords
  function: "hl-func",
  identifier: "hl-ident",
  number: "hl-num",
  string: "hl-str",
  comment: "hl-comment",
  operator: "hl-punct",
  space: "",
  unknown: "",
};

/**
 * Render a token array into React elements with highlighting + token click support.
 */
export function renderTokens(
  tokens: Token[],
  highlightToken: string | null,
): React.ReactNode[] {
  return tokens.map((tok, i) => {
    if (tok.type === "space") {
      return tok.text;
    }

    const cls = TYPE_CSS[tok.type] || "";
    const isActive = highlightToken !== null && tok.text === highlightToken;
    const needsSpan = cls || tok.navigable || isActive;

    if (!needsSpan) {
      return tok.text;
    }

    return (
      <span
        key={i}
        className={`${cls}${isActive ? " token-hl" : ""}${tok.navigable ? " nav-token" : ""}`}
        data-token={tok.text}
        data-navigable={tok.navigable ? "1" : undefined}
      >
        {tok.text}
      </span>
    );
  });
}

// ── Regex fallback (for when parser isn't loaded yet) ─────────

const C_KEYWORDS = new Set([
  "auto", "break", "case", "char", "const", "continue", "default", "do",
  "double", "else", "enum", "extern", "float", "for", "goto", "if",
  "int", "long", "register", "return", "short", "signed", "sizeof",
  "static", "struct", "switch", "typedef", "union", "unsigned", "void",
  "volatile", "while", "bool", "true", "false", "nullptr", "NULL",
  "__int8", "__int16", "__int32", "__int64", "__fastcall", "__cdecl",
  "__stdcall", "__thiscall", "_BYTE", "_WORD", "_DWORD", "_QWORD",
  "_BOOL", "LOBYTE", "HIBYTE", "LOWORD", "HIWORD",
]);

const TOKEN_RE =
  /("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')|(\b0x[0-9A-Fa-f]+\b|\b\d+\b)|(\b[A-Za-z_]\w*\b)|(\/\/.*$)|([^\w\s"']+)/g;

export function highlightCFallback(
  text: string,
  highlightToken: string | null,
): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  let lastIndex = 0;

  TOKEN_RE.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = TOKEN_RE.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.substring(lastIndex, match.index));
    }

    const [full, str, num, ident, comment] = match;
    const isActive = highlightToken !== null && full === highlightToken;
    const hlCls = isActive ? " token-hl" : "";

    if (str) {
      parts.push(<span key={match.index} className={`hl-str${hlCls}`} data-token={full}>{full}</span>);
    } else if (comment) {
      parts.push(<span key={match.index} className="hl-comment">{full}</span>);
    } else if (num) {
      parts.push(<span key={match.index} className={`hl-num${hlCls}`} data-token={full}>{full}</span>);
    } else if (ident) {
      const cls = C_KEYWORDS.has(ident) ? "hl-kw"
        : ident.startsWith("sub_") || ident.startsWith("loc_") ? "hl-func"
        : "hl-ident";
      parts.push(<span key={match.index} className={`${cls}${hlCls}`} data-token={full}>{full}</span>);
    } else {
      parts.push(<span key={match.index} className="hl-punct">{full}</span>);
    }

    lastIndex = match.index + full.length;
  }

  if (lastIndex < text.length) {
    parts.push(text.substring(lastIndex));
  }

  return parts;
}
