from weasyprint import HTML

from .exceptions import PDFRenderException


class PdfRenderer:
    """Renders HTML content into PDF bytes."""

    def render(self, html: str) -> bytes:
        try:
            return HTML(string=html).write_pdf()
        except Exception as e:
            raise PDFRenderException(str(e)) from e
