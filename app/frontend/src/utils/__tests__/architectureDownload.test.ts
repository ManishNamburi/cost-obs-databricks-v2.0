import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ARCHITECTURE_PDF_FILENAME,
  ARCHITECTURE_PDF_PATH,
  downloadArchitecturePdf,
} from "../architectureDownload";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("downloadArchitecturePdf", () => {
  it("downloads the committed v2 Lakebase architecture asset", async () => {
    const click = vi.fn();
    const remove = vi.fn();
    const anchor = { href: "", download: "", style: {}, click, remove };
    vi.spyOn(document, "createElement").mockReturnValue(anchor as unknown as HTMLAnchorElement);
    vi.spyOn(document.body, "appendChild").mockImplementation((node) => node);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      blob: async () => new Blob(["pdf"]),
    }));
    vi.stubGlobal("URL", {
      createObjectURL: vi.fn(() => "blob:architecture"),
      revokeObjectURL: vi.fn(),
    });

    await downloadArchitecturePdf();

    expect(fetch).toHaveBeenCalledWith(ARCHITECTURE_PDF_PATH);
    expect(anchor.download).toBe(ARCHITECTURE_PDF_FILENAME);
    expect(click).toHaveBeenCalledOnce();
    expect(remove).toHaveBeenCalledOnce();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:architecture");
  });

  it("fails instead of downloading an error response", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 404 }));
    await expect(downloadArchitecturePdf()).rejects.toThrow(
      "Architecture PDF download failed with status 404",
    );
  });
});
