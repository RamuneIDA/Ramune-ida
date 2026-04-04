/**
 * Navigation target detection for code views.
 */

// Pattern for IDA-generated names and hex addresses
const NAV_PATTERN = /\b(sub_[0-9A-Fa-f]+|loc_[0-9A-Fa-f]+|0x[0-9A-Fa-f]+)\b/g;

/**
 * Given a line of text and a column offset, find if there's a navigable
 * target at that position.
 */
export function findNavTarget(line: string, col: number): string | null {
  NAV_PATTERN.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = NAV_PATTERN.exec(line)) !== null) {
    const start = match.index;
    const end = start + match[0].length;
    if (col >= start && col <= end) {
      return match[0];
    }
  }
  return null;
}

/**
 * Check if a token is a valid navigation target.
 * Returns false for local variables, C keywords, type names, etc.
 */
export function isNavigable(token: string): boolean {
  // IDA names: sub_, loc_, off_, unk_, dword_, etc.
  if (/^(sub|loc|off|unk|dword|qword|byte|word|asc|stru|flt|dbl)_[0-9A-Fa-f]+$/.test(token)) {
    return true;
  }

  // Hex addresses
  if (/^0x[0-9A-Fa-f]+$/.test(token)) {
    return true;
  }

  // IDA type names — not navigable
  if (/^_(BYTE|WORD|DWORD|QWORD|BOOL|OWORD|TBYTE|UNKNOWN)$/.test(token)) {
    return false;
  }

  // Known library/external function names (start with _ or .)
  if (/^[._][A-Za-z]/.test(token)) {
    return true;
  }

  // Named functions (not starting with common variable prefixes)
  // Reject: v1, v2, a1, a2, s, i, j, result, etc.
  if (/^(v\d+|a\d+|s\d*|i|j|k|n|m|result|this|argc|argv|envp)$/.test(token)) {
    return false;
  }

  // Reject C keywords and IDA type names
  const REJECT = new Set([
    "auto", "break", "case", "char", "const", "continue", "default", "do",
    "double", "else", "enum", "extern", "float", "for", "goto", "if",
    "int", "long", "register", "return", "short", "signed", "sizeof",
    "static", "struct", "switch", "typedef", "union", "unsigned", "void",
    "volatile", "while", "bool", "true", "false", "nullptr", "NULL",
    "__int8", "__int16", "__int32", "__int64", "__fastcall", "__cdecl",
    "__stdcall", "__thiscall", "_BYTE", "_WORD", "_DWORD", "_QWORD",
    "_BOOL", "LOBYTE", "HIBYTE", "LOWORD", "HIWORD",
    // Common type-like tokens
    "BYREF", "near", "far",
  ]);
  if (REJECT.has(token)) {
    return false;
  }

  // Reject pure numbers
  if (/^\d+$/.test(token)) {
    return false;
  }

  // Accept anything else that looks like an identifier (likely a named symbol)
  if (/^[A-Za-z_]\w{2,}$/.test(token)) {
    return true;
  }

  return false;
}

/**
 * Find navigable target in disassembly lines.
 */
const DISASM_NAV =
  /\b(sub_[0-9A-Fa-f]+|loc_[0-9A-Fa-f]+|0x[0-9A-Fa-f]+|_[A-Za-z_][A-Za-z0-9_]*)\b/g;

export function findDisasmNavTarget(line: string, col: number): string | null {
  const callMatch = line.match(/\b(?:call|jmp)\s+/);
  if (!callMatch) {
    return findNavTarget(line, col);
  }

  DISASM_NAV.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = DISASM_NAV.exec(line)) !== null) {
    const start = match.index;
    const end = start + match[0].length;
    if (col >= start && col <= end) {
      return match[0];
    }
  }
  return null;
}
