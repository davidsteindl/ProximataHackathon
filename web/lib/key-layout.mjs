/** Keep the camera's reserved right edge in sync with the Key's responsive layout. */
export function observeKeyLayout(legend, viewport, onChange) {
  const sync = () => {
    const floating = legend.open && getComputedStyle(legend).position === "absolute";
    onChange(floating ? legend.offsetWidth + 16 : 0);
  };
  const observer = new ResizeObserver(sync);
  observer.observe(legend);
  observer.observe(viewport);
  // A breakpoint can change position without changing either observed box's size.
  window.addEventListener("resize", sync);
  sync();
  return () => {
    observer.disconnect();
    window.removeEventListener("resize", sync);
  };
}
