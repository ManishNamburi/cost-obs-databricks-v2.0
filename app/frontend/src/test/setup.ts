import "@testing-library/jest-dom";

// jsdom in this setup doesn't expose localStorage/sessionStorage, but components
// read them in useState initializers at render time (e.g. info-box minimize state).
// Provide a minimal in-memory Storage so those renders don't throw in tests.
class MemoryStorage implements Storage {
  private store = new Map<string, string>();
  get length() { return this.store.size; }
  clear() { this.store.clear(); }
  getItem(key: string) { return this.store.has(key) ? this.store.get(key)! : null; }
  key(index: number) { return Array.from(this.store.keys())[index] ?? null; }
  removeItem(key: string) { this.store.delete(key); }
  setItem(key: string, value: string) { this.store.set(key, String(value)); }
}

for (const name of ["localStorage", "sessionStorage"] as const) {
  const desc = Object.getOwnPropertyDescriptor(globalThis, name);
  if (!desc || desc.get?.() == null) {
    Object.defineProperty(globalThis, name, { value: new MemoryStorage(), writable: true, configurable: true });
  }
}
