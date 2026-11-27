import { createContext, useContext } from "react";
export const HistorySlotContext = createContext<HTMLElement | null>(null);
export const useHistorySlot = () => useContext(HistorySlotContext);
