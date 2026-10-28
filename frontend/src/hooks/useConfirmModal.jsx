import { useCallback, useEffect, useRef, useState } from "react";
import ConfirmModal from "../components/ConfirmModal";

/**
 * Promise-based in-app confirm. Drop-in for `window.confirm` without a native alert.
 *
 *   const { confirm, modal } = useConfirmModal();
 *   if (!(await confirm({ title, body, danger }))) return;
 *   const token = await confirm({ title, body, prompt: { label, type: "password" } });
 *   // render {modal} in the component tree
 */
export function useConfirmModal() {
  const [request, setRequest] = useState(null);
  const resolverRef = useRef(null);

  const settle = useCallback((value) => {
    const resolve = resolverRef.current;
    resolverRef.current = null;
    setRequest(null);
    resolve?.(value);
  }, []);

  useEffect(() => {
    return () => {
      if (resolverRef.current) {
        resolverRef.current(false);
        resolverRef.current = null;
      }
    };
  }, []);

  const onConfirm = useCallback(
    (value) => settle(typeof value === "string" ? value : true),
    [settle],
  );
  const onCancel = useCallback(() => settle(false), [settle]);

  const confirm = useCallback((options = {}) => {
    return new Promise((resolve) => {
      if (resolverRef.current) resolverRef.current(false);
      resolverRef.current = resolve;
      setRequest({
        title: options.title || "Please confirm",
        body: options.body || "",
        confirmLabel: options.confirmLabel || "Confirm",
        cancelLabel: options.cancelLabel || "Cancel",
        danger: Boolean(options.danger),
        prompt: options.prompt || null,
      });
    });
  }, []);

  const modal = (
    <ConfirmModal
      open={Boolean(request)}
      title={request?.title}
      body={request?.body}
      confirmLabel={request?.confirmLabel}
      cancelLabel={request?.cancelLabel}
      danger={Boolean(request?.danger)}
      prompt={request?.prompt || null}
      onConfirm={onConfirm}
      onCancel={onCancel}
    />
  );

  return { confirm, modal };
}
