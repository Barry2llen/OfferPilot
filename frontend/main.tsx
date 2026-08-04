import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource-variable/dm-sans/wght.css";
import "@fontsource-variable/outfit/wght.css";
import "@fontsource/roboto/latin-400.css";
import "@fontsource/roboto/latin-500.css";
import "@fontsource/roboto/latin-700.css";
import AppRouter from "@/app/router";
import "@/app/globals.css";

const rootElement = document.getElementById("root");

if (!rootElement) {
  throw new Error("OfferPilot root element is missing");
}

createRoot(rootElement).render(
  <StrictMode>
    <AppRouter />
  </StrictMode>
);
