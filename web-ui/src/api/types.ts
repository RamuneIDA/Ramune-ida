export interface ProjectSummary {
  project_id: string;
  has_database: boolean;
  worker_alive: boolean;
  exe_path: string | null;
  idb_path: string | null;
}

export interface ProjectDetail extends ProjectSummary {
  work_dir: string;
  last_accessed: number;
  active_tasks: TaskInfo[];
}

export interface TaskInfo {
  task_id: string;
  method: string;
  status: string;
}

export interface SystemInfo {
  instance_count: number;
  soft_limit: number;
  hard_limit: number;
  active_projects: string[];
  project_count: number;
}

export interface ProjectFile {
  name: string;
  size: number;
  modified: number;
}

export interface ActivityEvent {
  id: string;
  timestamp: number;
  tool_name: string;
  params_summary: string;
  status: "pending" | "completed" | "failed";
  project_id?: string;
  duration_ms?: number;
  kind: string;
}
