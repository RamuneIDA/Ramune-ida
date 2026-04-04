export interface Theme {
  id: string;
  name: string;
  colors: Record<string, string>;
}

export const themes: Theme[] = [
  {
    id: "catppuccin",
    name: "Catppuccin Mocha",
    colors: {
      "--bg-primary": "#1e1e2e",
      "--bg-secondary": "#181825",
      "--bg-header": "#11111b",
      "--bg-hover": "#313244",
      "--bg-active": "#45475a",
      "--border": "#313244",
      "--text-primary": "#cdd6f4",
      "--text-secondary": "#a6adc8",
      "--text-muted": "#585b70",
      "--accent": "#89b4fa",
      "--green": "#a6e3a1",
      "--red": "#f38ba8",
      "--yellow": "#f9e2af",
      "--orange": "#fab387",
    },
  },
  {
    id: "one-dark",
    name: "One Dark",
    colors: {
      "--bg-primary": "#282c34",
      "--bg-secondary": "#21252b",
      "--bg-header": "#1e2127",
      "--bg-hover": "#2c313c",
      "--bg-active": "#393f4a",
      "--border": "#3e4452",
      "--text-primary": "#abb2bf",
      "--text-secondary": "#8b95a7",
      "--text-muted": "#5c6370",
      "--accent": "#61afef",
      "--green": "#98c379",
      "--red": "#e06c75",
      "--yellow": "#e5c07b",
      "--orange": "#d19a66",
    },
  },
  {
    id: "dracula",
    name: "Dracula",
    colors: {
      "--bg-primary": "#282a36",
      "--bg-secondary": "#21222c",
      "--bg-header": "#191a21",
      "--bg-hover": "#343746",
      "--bg-active": "#44475a",
      "--border": "#44475a",
      "--text-primary": "#f8f8f2",
      "--text-secondary": "#bfbfbf",
      "--text-muted": "#6272a4",
      "--accent": "#8be9fd",
      "--green": "#50fa7b",
      "--red": "#ff5555",
      "--yellow": "#f1fa8c",
      "--orange": "#ffb86c",
    },
  },
  {
    id: "nord",
    name: "Nord",
    colors: {
      "--bg-primary": "#2e3440",
      "--bg-secondary": "#292e39",
      "--bg-header": "#242933",
      "--bg-hover": "#3b4252",
      "--bg-active": "#434c5e",
      "--border": "#3b4252",
      "--text-primary": "#d8dee9",
      "--text-secondary": "#a5b3c7",
      "--text-muted": "#616e88",
      "--accent": "#81a1c1",
      "--green": "#a3be8c",
      "--red": "#bf616a",
      "--yellow": "#ebcb8b",
      "--orange": "#d08770",
    },
  },
  {
    id: "tokyo-night",
    name: "Tokyo Night",
    colors: {
      "--bg-primary": "#1a1b26",
      "--bg-secondary": "#16161e",
      "--bg-header": "#13131a",
      "--bg-hover": "#292e42",
      "--bg-active": "#33467c",
      "--border": "#29293d",
      "--text-primary": "#a9b1d6",
      "--text-secondary": "#787c99",
      "--text-muted": "#565a6e",
      "--accent": "#7aa2f7",
      "--green": "#9ece6a",
      "--red": "#f7768e",
      "--yellow": "#e0af68",
      "--orange": "#ff9e64",
    },
  },
];

const LS_KEY = "ramune-web:theme";

export function getStoredThemeId(): string {
  return localStorage.getItem(LS_KEY) || "catppuccin";
}

export function applyTheme(themeId: string) {
  const theme = themes.find((t) => t.id === themeId) || themes[0];
  const root = document.documentElement;
  for (const [key, value] of Object.entries(theme.colors)) {
    root.style.setProperty(key, value);
  }
  localStorage.setItem(LS_KEY, theme.id);
}
