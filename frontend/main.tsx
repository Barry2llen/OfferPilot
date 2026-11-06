import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { I18nextProvider } from "react-i18next";
import "@fontsource-variable/dm-sans/wght.css";
import { initializeTheme } from "@/app/lib/theme";
import AppRouter from "@/app/router";
import "@/app/globals.css";
import i18n from "@/app/lib/i18n";

initializeTheme();

const rootElement = document.getElementById("root");

if (!rootElement) {
  throw new Error("OfferPilot root element is missing");
}

createRoot(rootElement).render(
  <StrictMode>
    <I18nextProvider i18n={i18n}>
      <AppRouter />
    </I18nextProvider>
  </StrictMode>
);
