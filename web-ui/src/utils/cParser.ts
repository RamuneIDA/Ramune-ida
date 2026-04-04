/**
 * C pseudocode parser using tree-sitter.
 *
 * Parses IDA's decompiler output into typed tokens for:
 * - Accurate syntax highlighting (no regex guessing)
 * - Navigation decisions (call targets are navigable, local vars aren't)
 */

/* eslint-disable @typescript-eslint/no-explicit-any */
let Parser: any = null;
let parser: any = null;
let initPromise: Promise<void> | null = null;

/** Token types that the UI cares about */
export type TokenType =
  | "keyword"       // C keywords (if, return, int, ...)
  | "type"          // type names (_QWORD, __int64, struct names)
  | "function"      // function name in call expression → navigable
  | "identifier"    // generic identifier (local var, param)
  | "number"        // numeric literals
  | "string"        // string literals
  | "comment"       // comments
  | "operator"      // operators, punctuation
  | "space"         // whitespace
  | "unknown";      // fallback

export interface Token {
  text: string;
  type: TokenType;
  navigable: boolean;  // can this token be double-clicked to navigate?
}

/** Initialize tree-sitter (call once, safe to call multiple times) */
export async function initParser(): Promise<void> {
  if (parser) return;
  if (initPromise) return initPromise;

  initPromise = (async () => {
    const mod = await import("web-tree-sitter");
    const P = mod.Parser || mod.default?.Parser || mod.default || mod;
    await P.init({
      locateFile: (file: string) => `/${file.replace("web-tree-sitter.wasm", "tree-sitter.wasm")}`,
    });
    const p = new P();
    const lang = await mod.Language.load("/tree-sitter-c.wasm");
    p.setLanguage(lang);
    Parser = P;
    parser = p;
  })();

  return initPromise;
}

/** Check if parser is ready */
export function isParserReady(): boolean {
  return parser !== null;
}

// Node types that represent type names
const TYPE_NODES = new Set([
  "primitive_type", "sized_type_specifier", "type_identifier",
]);

// Node types that represent keywords
const KEYWORD_NODES = new Set([
  "if", "else", "while", "for", "do", "switch", "case", "default",
  "break", "continue", "return", "goto", "sizeof", "typedef",
  "struct", "union", "enum", "const", "volatile", "static",
  "extern", "register", "auto", "signed", "unsigned",
  "true", "false", "NULL", "nullptr",
]);

/**
 * Parse a single line of C pseudocode into tokens.
 * Falls back to simple splitting if parser isn't ready.
 */
export function tokenizeLine(text: string): Token[] {
  if (!parser) {
    // Fallback: return as single unknown token
    return [{ text, type: "unknown", navigable: false }];
  }

  // Parse the line as if it were a complete translation unit.
  // Wrap in a function body to help the parser with context.
  const wrapped = `void __wrapper__() { ${text} }`;
  const tree = parser.parse(wrapped);
  const root = tree.rootNode;

  const tokens: Token[] = [];
  const offset = "void __wrapper__() { ".length;
  let lastEnd = 0;

  // Walk all leaf nodes and extract tokens
  function walk(node: any) {
    if (node.childCount === 0) {
      // Leaf node — this is a token
      const start = node.startIndex - offset;
      const end = node.endIndex - offset;

      // Skip tokens outside our line
      if (end <= 0 || start >= text.length) return;

      const clampStart = Math.max(0, start);
      const clampEnd = Math.min(text.length, end);

      // Fill gap with whitespace/unknown
      if (clampStart > lastEnd) {
        const gap = text.substring(lastEnd, clampStart);
        if (gap.trim() === "") {
          tokens.push({ text: gap, type: "space", navigable: false });
        } else {
          tokens.push({ text: gap, type: "unknown", navigable: false });
        }
      }

      const tokenText = text.substring(clampStart, clampEnd);
      if (tokenText.length === 0) return;

      const tokenInfo = classifyNode(node, tokenText);
      tokens.push(tokenInfo);
      lastEnd = clampEnd;
    } else {
      for (let i = 0; i < node.childCount; i++) {
        walk(node.child(i)!);
      }
    }
  }

  walk(root);

  // Trailing text
  if (lastEnd < text.length) {
    const rest = text.substring(lastEnd);
    tokens.push({ text: rest, type: rest.trim() === "" ? "space" : "unknown", navigable: false });
  }

  tree?.delete();
  return tokens;
}

function classifyNode(node: any, text: string): Token {
  const nodeType = node.type;
  const parent = node.parent;
  const parentType = parent?.type || "";

  // Comments
  if (nodeType === "comment") {
    return { text, type: "comment", navigable: false };
  }

  // String/char literals
  if (nodeType === "string_literal" || nodeType === "char_literal" ||
      nodeType === "string_content" || nodeType === "escape_sequence" ||
      nodeType === '"' || nodeType === "'") {
    return { text, type: "string", navigable: false };
  }

  // Number literals
  if (nodeType === "number_literal") {
    return { text, type: "number", navigable: false };
  }

  // Type names
  if (TYPE_NODES.has(nodeType)) {
    return { text, type: "type", navigable: false };
  }

  // Keywords
  if (KEYWORD_NODES.has(text) || nodeType.endsWith("_specifier")) {
    return { text, type: "keyword", navigable: false };
  }

  // Label identifiers (goto LABEL_5, LABEL_5:)
  if (nodeType === "statement_identifier") {
    return { text, type: "function", navigable: true };
  }

  // Identifiers — blacklist approach: navigable unless proven local/trivial
  if (nodeType === "identifier" || nodeType === "field_identifier") {
    // Function call target → always navigable
    if (parentType === "call_expression" && parent?.child(0) === node) {
      return { text, type: "function", navigable: true };
    }

    // Declaration / parameter → local variable, not navigable
    if (parentType === "declaration" || parentType === "parameter_declaration" ||
        parentType === "init_declarator") {
      return { text, type: "identifier", navigable: false };
    }

    // Known local variable patterns (IDA-generated names)
    if (/^(v\d+|a\d+|s\d*|i|j|k|n|m|result|this|argc|argv|envp)$/.test(text)) {
      return { text, type: "identifier", navigable: false };
    }

    // Single character identifiers → likely loop vars
    if (text.length === 1) {
      return { text, type: "identifier", navigable: false };
    }

    // Everything else: likely a global symbol (function, variable, string ref) → navigable
    return { text, type: "function", navigable: true };
  }

  // Operators and punctuation
  if (/^[{}\[\]();,=+\-*\/%&|^~!<>?:.]/.test(text) || nodeType === "operator") {
    return { text, type: "operator", navigable: false };
  }

  // Fallback
  return { text, type: "unknown", navigable: false };
}

/**
 * Parse a full pseudocode text (all lines at once) for better context.
 * Returns array of token arrays (one per line).
 */
export function tokenizeCode(code: string): Token[][] {
  const lines = code.split("\n");
  return lines.map((line) => tokenizeLine(line));
}
