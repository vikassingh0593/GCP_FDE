import {defineConfig} from 'vite';
export default defineConfig({
  server: {host: '127.0.0.1', port: 5173},
  resolve: {dedupe: ['lit', '@a2ui/web_core']},
});
