import { type ReactNode, useEffect, useRef } from "react";


interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  children: ReactNode;
}

export default function Modal({ isOpen, onClose, children }: ModalProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialogElement = dialogRef.current;
    if (!dialogElement) return;

    if (isOpen) {
      dialogElement.showModal(); 
    } else {
      dialogElement.close();
    }
  }, [isOpen]);

  const handleCancel = (e: React.SyntheticEvent) => {
    e.preventDefault();
    onClose();
  };

  return (
    <dialog 
      ref={dialogRef} 
      onCancel={handleCancel}
      className="custom-modal"
    >
      <div className="modal-content">
        <button className="close-btn" onClick={onClose}>
          &times;
        </button>
        {children}
      </div>
    </dialog>
  );
}
