import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
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
