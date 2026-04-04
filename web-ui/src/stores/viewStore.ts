import { create } from "zustand";
import { decompile, disasm } from "../api/client";

interface ViewState {
  // Current navigation target
  currentFunc: string | null;
  currentAddr: string | null;

  // Decompile result
  decompileCode: string | null;
  decompileLoading: boolean;
  decompileError: string | null;

  // Disasm result
  disasmText: string | null;
  disasmLoading: boolean;
  disasmError: string | null;

  // Navigation history
  history: string[];
  historyIndex: number;

  // Cache
  _decompileCache: Map<string, string>;

  navigateTo: (projectId: string, func: string) => void;
  goBack: () => void;
  clear: () => void;
}

export const useViewStore = create<ViewState>((set, get) => ({
  currentFunc: null,
  currentAddr: null,
  decompileCode: null,
  decompileLoading: false,
  decompileError: null,
  disasmText: null,
  disasmLoading: false,
  disasmError: null,
  history: [],
  historyIndex: -1,
  _decompileCache: new Map(),

  navigateTo: (projectId: string, func: string) => {
    const state = get();

    // Update history
    const newHistory = state.history.slice(0, state.historyIndex + 1);
    newHistory.push(func);

    set({
      currentFunc: func,
      currentAddr: func,
      history: newHistory,
      historyIndex: newHistory.length - 1,
      decompileLoading: true,
      decompileError: null,
      disasmLoading: true,
      disasmError: null,
    });

    // Check cache
    const cacheKey = `${projectId}:${func}`;
    const cached = state._decompileCache.get(cacheKey);
    if (cached) {
      set({ decompileCode: cached, decompileLoading: false });
    } else {
      decompile(projectId, func)
        .then((res) => {
          const code = (res as Record<string, unknown>).code as string || JSON.stringify(res, null, 2);
          // Update cache (keep max 50 entries)
          const cache = get()._decompileCache;
          if (cache.size > 50) {
            const first = cache.keys().next().value;
            if (first) cache.delete(first);
          }
          cache.set(cacheKey, code);
          set({ decompileCode: code, decompileLoading: false });
        })
        .catch((e) => {
          set({ decompileCode: null, decompileLoading: false, decompileError: String(e) });
        });
    }

    // Fetch disasm
    disasm(projectId, func, "500")
      .then((res) => {
        const text = (res as Record<string, unknown>).disasm as string || JSON.stringify(res, null, 2);
        set({ disasmText: text, disasmLoading: false });
      })
      .catch((e) => {
        set({ disasmText: null, disasmLoading: false, disasmError: String(e) });
      });
  },

  goBack: () => {
    const state = get();
    if (state.historyIndex <= 0) return;
    const newIndex = state.historyIndex - 1;
    const func = state.history[newIndex];
    set({ historyIndex: newIndex, currentFunc: func, currentAddr: func });
    // Note: re-navigation would need projectId, simplified for now
  },

  clear: () => {
    set({
      currentFunc: null,
      currentAddr: null,
      decompileCode: null,
      decompileError: null,
      disasmText: null,
      disasmError: null,
      history: [],
      historyIndex: -1,
    });
  },
}));
