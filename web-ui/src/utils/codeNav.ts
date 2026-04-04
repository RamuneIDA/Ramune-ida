/**
 * Extract a navigable target (function name or address) from code text
 * at the given character position.
 *
 * Matches: sub_xxxx, loc_xxxx, 0xHEX, and known function names from
 * the function list.
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
 * Find navigable target in disassembly lines.
 * Also matches call/jmp operands like _funcname, __printf_chk, etc.
 */
const DISASM_NAV =
  /\b(sub_[0-9A-Fa-f]+|loc_[0-9A-Fa-f]+|0x[0-9A-Fa-f]+|_[A-Za-z_][A-Za-z0-9_]*)\b/g;

export function findDisasmNavTarget(line: string, col: number): string | null {
  // Only consider targets after call/jmp instructions
  const callMatch = line.match(/\b(?:call|jmp)\s+/);
  if (!callMatch) {
    // Still try sub_/loc_/0x anywhere
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
