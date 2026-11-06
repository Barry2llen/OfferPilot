import type { ReactNode } from "react";
import Modal from "./modal";
export default function FormDrawer(props: { busy?: boolean; open: boolean; title: string; children: ReactNode; onClose: () => void }) {
  return <Modal {...props} drawer />;
}
