/** Leave the app for a URL (a signed download link). A module of its own so tests can stand in for it. */
export function goTo(url: string): void {
  window.location.assign(url);
}
