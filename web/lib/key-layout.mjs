/** Keep the camera's reserved right edge in sync with a floating right overlay (the info panel); closed <details> or in-flow (narrow) overlays reserve nothing. */
export function observeRightOverlay(overlay, viewport, onChange) {
  const sync = () => {
    const floating = overlay.open !== false && getComputedStyle(overlay).position === "absolute";
    onChange(floating ? overlay.offsetWidth + 16 : 0);
  };
  const observer = new ResizeObserver(sync);
  observer.observe(overlay);
  observer.observe(viewport);
  // A breakpoint can change position without changing either observed box's size.
  window.addEventListener("resize", sync);
  sync();
  return () => {
    observer.disconnect();
    window.removeEventListener("resize", sync);
  };
}
