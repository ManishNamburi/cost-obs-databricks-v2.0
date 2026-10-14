export const ARCHITECTURE_PDF_PATH = "/reports/cost-obs-architecture-v2.pdf";
export const ARCHITECTURE_PDF_FILENAME = "cost-obs-architecture-v2.pdf";

export async function downloadArchitecturePdf(): Promise<void> {
  const response = await fetch(ARCHITECTURE_PDF_PATH);
  if (!response.ok) {
    throw new Error(`Architecture PDF download failed with status ${response.status}`);
  }

  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  try {
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = ARCHITECTURE_PDF_FILENAME;
    link.style.display = "none";
    document.body.appendChild(link);
    try {
      link.click();
    } finally {
      link.remove();
    }
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}
