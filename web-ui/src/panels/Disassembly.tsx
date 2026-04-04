import { useEffect, useRef } from "react";
import { EditorView } from "@codemirror/view";
import { EditorState } from "@codemirror/state";
import { oneDark } from "@codemirror/theme-one-dark";
import { highlightSelectionMatches } from "@codemirror/search";
import { useViewStore } from "../stores/viewStore";
import { useProjectStore } from "../stores/projectStore";
import { findDisasmNavTarget } from "../utils/codeNav";

export function Disassembly() {
  const { currentAddr, disasmText, disasmLoading, disasmError } =
    useViewStore();
  const editorRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<EditorView | null>(null);

  useEffect(() => {
    if (!editorRef.current) return;

    const view = new EditorView({
      state: EditorState.create({
        doc: "",
        extensions: [
          oneDark,
          highlightSelectionMatches(),
          EditorView.editable.of(false),
          EditorView.lineWrapping,
          EditorState.readOnly.of(true),
          EditorView.domEventHandlers({
            click(event, view) {
              if (!event.ctrlKey && !event.metaKey) return false;
              const pos = view.posAtCoords({ x: event.clientX, y: event.clientY });
              if (pos === null) return false;
              const line = view.state.doc.lineAt(pos);
              const col = pos - line.from;
              const target = findDisasmNavTarget(line.text, col);
              if (target) {
                event.preventDefault();
                const pid = useProjectStore.getState().activeProjectId;
                if (pid) {
                  useViewStore.getState().navigateTo(pid, target);
                }
                return true;
              }
              return false;
            },
          }),
        ],
      }),
      parent: editorRef.current,
    });
    viewRef.current = view;

    return () => {
      view.destroy();
      viewRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!viewRef.current) return;
    const doc = disasmText || "";
    viewRef.current.dispatch({
      changes: {
        from: 0,
        to: viewRef.current.state.doc.length,
        insert: doc,
      },
    });
  }, [disasmText]);

  return (
    <div className="panel disasm-panel">
      <div className="panel-header">
        <span>Disassembly{currentAddr ? `: ${currentAddr}` : ""}</span>
      </div>
      <div className="panel-body code-panel-body">
        {disasmLoading && (
          <div className="code-overlay">Loading...</div>
        )}
        {disasmError && (
          <div className="code-overlay error-msg">{disasmError}</div>
        )}
        {!currentAddr && !disasmLoading && (
          <div className="empty-hint">
            Select a function from the list
            <br />
            <span className="empty-hint-sub">Ctrl+Click targets to navigate</span>
          </div>
        )}
        <div
          ref={editorRef}
          className="code-editor"
          style={{ display: currentAddr ? "block" : "none" }}
        />
      </div>
    </div>
  );
}
