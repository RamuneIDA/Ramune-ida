import { useProjectStore } from "../stores/projectStore";
import { useActivityStore } from "../stores/activityStore";

export function StatusBar() {
  const { activeProjectId, system } = useProjectStore();
  const { connected } = useActivityStore();

  return (
    <div className="status-bar">
      <span className="status-item">
        {activeProjectId ? `Project: ${activeProjectId}` : "No project"}
      </span>
      {system && (
        <span className="status-item">
          Workers: {system.instance_count}/{system.hard_limit || "∞"}
        </span>
      )}
      <span className="status-item">
        <span
          className={`status-dot ${connected ? "connected" : "disconnected"}`}
        />
        {connected ? "Live" : "Disconnected"}
      </span>
    </div>
  );
}
