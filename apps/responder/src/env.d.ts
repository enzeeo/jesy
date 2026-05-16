interface ImportMetaEnv {
  readonly VITE_DATA_MODE: 'fixture' | 'api';
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_MAPBOX_PUBLIC_TOKEN?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
