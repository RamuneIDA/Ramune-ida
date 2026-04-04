import { useEffect, useRef, useCallback } from "react";
import DockLayout from "rc-dock";
import type { LayoutData, TabData, TabGroup } from "rc-dock";
import "rc-dock/dist/rc-dock-dark.css";

import { Toolbar } from "./components/Toolbar";
import { StatusBar } from "./components/StatusBar";
import { ActivityStream } from "./panels/ActivityStream";
import { ProjectOverview } from "./panels/ProjectOverview";
import { FunctionList } from "./panels/FunctionList";
import { StringList } from "./panels/StringList";
import { Decompile } from "./panels/Decompile";
import { Disassembly } from "./panels/Disassembly";
import { HexView } from "./panels/HexView";
import { useProjectStore } from "./stores/projectStore";
import { useViewStore } from "./stores/viewStore";
import {
  connectActivityStream,
  disconnectActivityStream,
} from "./stores/activityStore";
import { applyTheme, getStoredThemeId } from "./theme/themes";
import "./App.css";

// ── Panel type registry ─────────────────────────────────────────

const PANEL_TYPES: Record<string, { title: string; render: () => React.ReactElement }> = {
  functions:   { title: "Functions",    render: () => <FunctionList /> },
  strings:     { title: "Strings",      render: () => <StringList /> },
  hex:         { title: "Hex",          render: () => <HexView /> },
  project:     { title: "Project",      render: () => <ProjectOverview /> },
  decompile:   { title: "Decompile",    render: () => <Decompile /> },
  disassembly: { title: "Disassembly",  render: () => <Disassembly /> },
  activity:    { title: "Activity",     render: () => <ActivityStream /> },
};

const PANEL_TITLES: Record<string, string> = Object.fromEntries(
  Object.entries(PANEL_TYPES).map(([k, v]) => [k, v.title]),
);

function parseTabType(id: string): string {
  const colon = id.indexOf(":");
  return colon >= 0 ? id.substring(0, colon) : id;
}

let tabCounter = 100;

function makeTab(id: string): TabData {
  const type = parseTabType(id);
  const reg = PANEL_TYPES[type];
  if (!reg) return { id, title: id, content: <div>Unknown: {id}</div>, group: "card" };
  return {
    id,
    title: reg.title,
    content: <div style={{ height: "100%", overflow: "auto" }}>{reg.render()}</div>,
    closable: true,
    group: "card",
  };
}

function createNewTab(type: string): TabData {
  return makeTab(`${type}:${++tabCounter}`);
}

function loadTab(data: TabData): TabData {
  const id = data.id!;
  const type = parseTabType(id);
  const reg = PANEL_TYPES[type];
  if (!reg) return { ...data, content: <div>Unknown: {id}</div> };
  return {
    ...data,
    title: reg.title,
    content: <div style={{ height: "100%", overflow: "auto" }}>{reg.render()}</div>,
    closable: true,
    group: "card",
  };
}

// ── Layout ──────────────────────────────────────────────────────

const groups: Record<string, TabGroup> = {
  card: {
    floatable: true,
    maximizable: true,
    animated: false,
  },
};

const LS_KEY = "ramune-web:dock-layout-v3";

function createDefaultLayout(): LayoutData {
  return {
    dockbox: {
      mode: "horizontal",
      children: [
        {
          size: 250,
          tabs: [makeTab("functions"), makeTab("strings"), makeTab("hex"), makeTab("project")],
          activeId: "project",
        },
        { size: 500, tabs: [makeTab("decompile")] },
        { size: 500, tabs: [makeTab("disassembly")] },
        { size: 300, tabs: [makeTab("activity")] },
      ],
    },
  };
}

function loadSavedLayout(): LayoutData | null {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed?.dockbox) return parsed;
  } catch {}
  localStorage.removeItem(LS_KEY);
  return null;
}

// ── App ─────────────────────────────────────────────────────────

function App() {
  const { fetchProjects, fetchSystem, activeProjectId } = useProjectStore();
  const clearView = useViewStore((s) => s.clear);
  const dockRef = useRef<DockLayout>(null);

  // Apply saved theme on mount
  useEffect(() => {
    applyTheme(getStoredThemeId());
  }, []);

  useEffect(() => { clearView(); }, [activeProjectId, clearView]);

  useEffect(() => {
    if (activeProjectId) {
      localStorage.setItem("ramune-web:active-project", activeProjectId);
    }
  }, [activeProjectId]);

  useEffect(() => {
    const saved = localStorage.getItem("ramune-web:active-project");
    if (saved) useProjectStore.getState().setActiveProject(saved);

    fetchProjects();
    fetchSystem();
    connectActivityStream();

    const interval = setInterval(() => {
      fetchProjects();
      fetchSystem();
    }, 5000);

    return () => {
      clearInterval(interval);
      disconnectActivityStream();
    };
  }, [fetchProjects, fetchSystem]);

  const onLayoutChange = useCallback(() => {
    try {
      const layout = dockRef.current?.saveLayout();
      if (layout) localStorage.setItem(LS_KEY, JSON.stringify(layout));
    } catch {}
  }, []);

  const handleAddPanel = useCallback((type: string) => {
    if (!dockRef.current) return;
    dockRef.current.dockMove(createNewTab(type), null, "float");
  }, []);

  const handleResetLayout = useCallback(() => {
    localStorage.removeItem(LS_KEY);
    window.location.reload();
  }, []);

  return (
    <div className="app-root">
      <Toolbar
        onAddPanel={handleAddPanel}
        onResetLayout={handleResetLayout}
        panelTypes={PANEL_TITLES}
      />
      <div className="app-main">
        <DockLayout
          ref={dockRef}
          defaultLayout={loadSavedLayout() || createDefaultLayout()}
          loadTab={loadTab}
          groups={groups}
          onLayoutChange={onLayoutChange}
          style={{ position: "absolute", left: 0, top: 0, right: 0, bottom: 0 }}
        />
      </div>
      <StatusBar />
    </div>
  );
}

export default App;
