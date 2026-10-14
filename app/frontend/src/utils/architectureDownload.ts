export const ARCHITECTURE_PDF_PATH = "/api/settings/architecture-pdf";
export const ARCHITECTURE_PDF_FILENAME = "cost-obs-architecture-v2.pdf";

function isPdfBytes(bytes: Uint8Array): boolean {
  return bytes.length >= 5
    && bytes[0] === 0x25
    && bytes[1] === 0x50
    && bytes[2] === 0x44
    && bytes[3] === 0x46
    && bytes[4] === 0x2d;
}

export async function downloadArchitecturePdf(): Promise<void> {
  const response = await fetch(ARCHITECTURE_PDF_PATH);
  if (!response.ok) {
    throw new Error(`Architecture PDF download failed with status ${response.status}`);
  }

  const buffer = await response.arrayBuffer();
  const bytes = new Uint8Array(buffer);
  if (!isPdfBytes(bytes)) {
    throw new Error("Architecture PDF download did not return a PDF");
  }

  const blob = new Blob([buffer], { type: "application/pdf" });
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = ARCHITECTURE_PDF_FILENAME;
  link.style.display = "none";
  document.body.appendChild(link);
  try {
    link.click();
    await new Promise((resolve) => window.setTimeout(resolve, 500));
  } finally {
    link.remove();
    URL.revokeObjectURL(objectUrl);
  }
}
