import { useEffect, useState } from "react";
import { useProjectStore } from "../stores/projectStore";
import { useViewStore } from "../stores/viewStore";

const BYTES_PER_ROW = 16;
const DEFAULT_SIZE = 256;

function formatHex(byte: number): string {
  return byte.toString(16).padStart(2, "0");
}

function formatAscii(byte: number): string {
  return byte >= 0x20 && byte < 0x7f ? String.fromCharCode(byte) : ".";
}

function parseHexString(hex: string): number[] {
  const bytes: number[] = [];
  for (let i = 0; i < hex.length; i += 2) {
    bytes.push(parseInt(hex.substring(i, i + 2), 16));
  }
  return bytes;
}

async function fetchBytes(
  pid: string,
  addr: string,
  size: number,
): Promise<{ addr: string; bytes: number[] }> {
  const res = await fetch(
    `/api/projects/${pid}/bytes?addr=${encodeURIComponent(addr)}&size=${size}`,
  );
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();
  return { addr: data.addr, bytes: parseHexString(data.bytes || "") };
}

export function HexView() {
  const { activeProjectId } = useProjectStore();
  const { currentAddr } = useViewStore();
  const [bytes, setBytes] = useState<number[]>([]);
  const [baseAddr, setBaseAddr] = useState<number>(0);
  const [loading, setLoading] = useState(false);
  const [addrInput, setAddrInput] = useState("");

  useEffect(() => {
    if (!activeProjectId || !currentAddr) return;
    setLoading(true);
    fetchBytes(activeProjectId, currentAddr, DEFAULT_SIZE)
      .then((data) => {
        setBytes(data.bytes);
        setBaseAddr(parseInt(data.addr, 16) || 0);
        setAddrInput(data.addr);
      })
      .catch(() => setBytes([]))
      .finally(() => setLoading(false));
  }, [activeProjectId, currentAddr]);

  const handleGo = () => {
    if (!activeProjectId || !addrInput) return;
    setLoading(true);
    fetchBytes(activeProjectId, addrInput, DEFAULT_SIZE)
      .then((data) => {
        setBytes(data.bytes);
        setBaseAddr(parseInt(data.addr, 16) || 0);
      })
      .catch(() => setBytes([]))
      .finally(() => setLoading(false));
  };

  const rows: number[][] = [];
  for (let i = 0; i < bytes.length; i += BYTES_PER_ROW) {
    rows.push(bytes.slice(i, i + BYTES_PER_ROW));
  }

  return (
    <div className="panel hex-panel">
      <div className="panel-header">
        <span>Hex</span>
        <div className="hex-addr-input-wrap">
          <input
            className="hex-addr-input"
            value={addrInput}
            onChange={(e) => setAddrInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleGo()}
            placeholder="Address..."
          />
        </div>
      </div>
      <div className="panel-body hex-body">
        {loading && <div className="empty-hint">Loading...</div>}
        {!loading && bytes.length === 0 && (
          <div className="empty-hint">No data</div>
        )}
        {!loading && rows.length > 0 && (
          <table className="hex-table">
            <tbody>
              {rows.map((row, rowIdx) => {
                const addr = baseAddr + rowIdx * BYTES_PER_ROW;
                return (
                  <tr key={rowIdx}>
                    <td className="hex-addr">
                      {addr.toString(16).padStart(8, "0")}
                    </td>
                    <td className="hex-bytes">
                      {row.map((b, i) => (
                        <span key={i} className="hex-byte">
                          {formatHex(b)}
                        </span>
                      ))}
                    </td>
                    <td className="hex-ascii">
                      {row.map((b, i) => (
                        <span key={i}>{formatAscii(b)}</span>
                      ))}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
