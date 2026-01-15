"""
PDF Converter Service - Convert PPTX to PDF using PowerPoint COM automation (Windows)
"""
import os
import sys
from pathlib import Path


def convert_pptx_to_pdf(pptx_path: str, pdf_path: str = None) -> str:
    """
    Convert PPTX file to PDF using PowerPoint COM automation (Windows only)

    Args:
        pptx_path: Path to input PPTX file
        pdf_path: Optional output PDF path (defaults to same name with .pdf extension)

    Returns:
        str: Path to generated PDF file

    Raises:
        Exception: If conversion fails or not on Windows
    """
    # Verify we're on Windows
    if sys.platform != 'win32':
        raise Exception("PDF conversion via COM automation requires Windows with PowerPoint installed")

    # Verify PPTX exists
    pptx_path = Path(pptx_path).resolve()
    if not pptx_path.exists():
        raise FileNotFoundError(f"PPTX file not found: {pptx_path}")

    # Default PDF path
    if pdf_path is None:
        pdf_path = pptx_path.with_suffix('.pdf')
    else:
        pdf_path = Path(pdf_path).resolve()

    # Ensure parent directory exists
    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        # Import COM automation library
        import comtypes.client

        print(f"📄 Converting PPTX to PDF...")
        print(f"   Input:  {pptx_path}")
        print(f"   Output: {pdf_path}")

        # Start PowerPoint
        powerpoint = comtypes.client.CreateObject("Powerpoint.Application")
        powerpoint.Visible = 1  # Make visible for debugging (optional)

        # Open presentation
        presentation = powerpoint.Presentations.Open(str(pptx_path), WithWindow=False)

        # Save as PDF (format 32 = ppSaveAsPDF)
        # See: https://docs.microsoft.com/en-us/office/vba/api/powerpoint.ppsaveasfiletype
        presentation.SaveAs(str(pdf_path), 32)

        # Close presentation and PowerPoint
        presentation.Close()
        powerpoint.Quit()

        print(f"   ✅ PDF created successfully: {pdf_path.name}")

        return str(pdf_path)

    except ImportError:
        raise Exception(
            "comtypes library not installed. "
            "Install with: pip install comtypes"
        )
    except Exception as e:
        # Clean up PowerPoint if it's still running
        try:
            if 'powerpoint' in locals():
                powerpoint.Quit()
        except:
            pass

        raise Exception(f"PDF conversion failed: {str(e)}")


async def convert_pptx_to_pdf_async(pptx_path: str, pdf_path: str = None) -> str:
    """
    Async wrapper for convert_pptx_to_pdf

    Args:
        pptx_path: Path to input PPTX file
        pdf_path: Optional output PDF path

    Returns:
        str: Path to generated PDF file
    """
    import asyncio

    # Run synchronous conversion in thread pool to avoid blocking
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        convert_pptx_to_pdf,
        pptx_path,
        pdf_path
    )


# For testing
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python pdf_converter.py <pptx_file> [output_pdf]")
        sys.exit(1)

    input_pptx = sys.argv[1]
    output_pdf = sys.argv[2] if len(sys.argv) > 2 else None

    try:
        result = convert_pptx_to_pdf(input_pptx, output_pdf)
        print(f"\n✅ Success! PDF saved to: {result}")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)
