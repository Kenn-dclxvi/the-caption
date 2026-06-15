import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const APP_PORT = Number(process.env.PORT || 3001);
const HMR_PORT = Number(process.env.VITE_HMR_PORT || 3002);

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    allowedHosts: ["mac-mini-2024"],
    host: "0.0.0.0",
    hmr: {
      clientPort: HMR_PORT,
      host: "0.0.0.0",
      port: HMR_PORT
    },
    port: APP_PORT
  }
});
