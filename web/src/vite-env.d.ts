/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL of the Modal job API (Task A7). Unset or empty means mock mode. */
  readonly VITE_API_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
