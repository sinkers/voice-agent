import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: false,
    // Provide a stub VITE_API_URL so api.ts can be imported in tests
    define: {
      "import.meta.env.VITE_API_URL": JSON.stringify("http://localhost:3000"),
    },
  },
});
