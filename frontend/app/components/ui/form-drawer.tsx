import Modal, { type ModalProps } from "./modal";
export default function FormDrawer(props: Omit<ModalProps, "drawer">) {
  return <Modal {...props} drawer />;
}
