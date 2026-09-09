"""
PDF Loader

Extracts text from PDF files using pymupdf with page-number tracking.
Auto-detects doc_type from folder path and company from filename.
"""

try:
    import fitz  # pymupdf
except ImportError:
    fitz = None
from pathlib import Path
from dataclasses import dataclass, field
from loguru import logger


@dataclass
class Document:
    """A loaded document page with metadata."""
    text: str
    metadata: dict = field(default_factory=dict)


def detect_doc_type(file_path: Path) -> str:
    """
    Auto-detect document type from the parent folder name.

    Folder conventions:
        interview_experiences/ → "interview_experience"
        job_descriptions/     → "job_description"
        aptitude_material/    → "aptitude_material"
    """
    parent = file_path.parent.name.lower()
    mapping = {
        "interview_experiences": "interview_experience",
        "interview_experience": "interview_experience",
        "job_descriptions": "job_description",
        "job_description": "job_description",
        "aptitude_material": "aptitude_material",
        "aptitude_materials": "aptitude_material",
        "aptitude": "aptitude_material",
    }
    return mapping.get(parent, "unknown")


def extract_company_name(file_path: Path) -> str:
    """
    Extract company name from filename.

    Conventions:
        Amazon.pdf → "Amazon"
        ProcDNA_JD.pdf → "ProcDNA"
        Interview_Experience_Walmart.pdf → "Walmart"
    """
    stem = file_path.stem  # filename without extension

    # Remove common prefixes/suffixes
    for prefix in ["Interview_Experience_", "interview_experience_", "IE_"]:
        if stem.startswith(prefix):
            stem = stem[len(prefix):]

    for suffix in ["_JD", "_jd", "_Job_Description", "_interview_experience", "_IE"]:
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]

    # Clean up remaining underscores at edges
    return stem.strip("_").replace("_", " ") if "_" in stem and len(stem.split("_")) > 2 else stem.strip("_")


def load_pdf(file_path: str | Path) -> list[Document]:
    """
    Load a PDF file and extract text page by page.

    Args:
        file_path: Path to the PDF file

    Returns:
        List of Document objects, one per page, with metadata:
            - source_file: filename
            - source_path: full path
            - page_number: 1-indexed page number
            - doc_type: auto-detected document type
            - company: extracted company name
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"PDF not found: {file_path}")
    if not file_path.suffix.lower() == ".pdf":
        raise ValueError(f"Not a PDF file: {file_path}")

    doc_type = detect_doc_type(file_path)
    company = extract_company_name(file_path)

    logger.info(
        f"Loading PDF: {file_path.name} | "
        f"doc_type={doc_type} | company={company}"
    )

    if fitz is None:
        logger.error("PyMuPDF (fitz) is not available. Cannot load PDF.")
        return []
    documents = []
    try:
        pdf = fitz.open(str(file_path))
        for page_num in range(len(pdf)):
            page = pdf[page_num]
            text = page.get_text("text").strip()

            if not text:
                logger.debug(f"Skipping empty page {page_num + 1} in {file_path.name}")
                continue

            doc = Document(
                text=text,
                metadata={
                    "source_file": file_path.name,
                    "source_path": str(file_path),
                    "page_number": page_num + 1,
                    "doc_type": doc_type,
                    "company": company,
                    "total_pages": len(pdf),
                },
            )
            documents.append(doc)
        pdf.close()
    except Exception as e:
        logger.error(f"Error loading PDF {file_path.name}: {e}")
        raise

    logger.info(f"Loaded {len(documents)} pages from {file_path.name}")
    return documents


def load_pdfs_from_directory(directory: str | Path) -> list[Document]:
    """
    Recursively load all PDFs from a directory.

    Expected structure:
        data/
        ├── interview_experiences/
        │   ├── Amazon.pdf
        │   └── ProcDNA.pdf
        ├── job_descriptions/
        │   └── ProcDNA_JD.pdf
        └── aptitude_material/
            └── SQL.pdf
    """
    directory = Path(directory)
    if not directory.exists():
        raise FileNotFoundError(f"Directory not found: {directory}")

    all_documents = []
    pdf_files = sorted(directory.rglob("*.pdf"))

    logger.info(f"Found {len(pdf_files)} PDF files in {directory}")

    for pdf_path in pdf_files:
        try:
            docs = load_pdf(pdf_path)
            all_documents.extend(docs)
        except Exception as e:
            logger.error(f"Skipping {pdf_path.name}: {e}")

    logger.info(
        f"Total loaded: {len(all_documents)} pages from "
        f"{len(pdf_files)} files"
    )
    return all_documents
