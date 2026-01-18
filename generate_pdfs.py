#!/usr/bin/env python3
"""
Baxter's Hot Rod Tuner Manual PDF Generator
Converts Markdown manuals to PDF format using pandoc and wkhtmltopdf

Requirements:
- Python 3.8+
- pandoc (https://pandoc.org/)
- wkhtmltopdf (https://wkhtmltopdf.org/)

Installation:
pip install pypandoc
# Install pandoc and wkhtmltopdf system-wide
"""

import os
import sys
import subprocess
from pathlib import Path

def check_dependencies():
    """Check if required tools are installed"""
    try:
        subprocess.run(['pandoc', '--version'], capture_output=True, check=True)
        print("✓ pandoc found")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("✗ pandoc not found. Please install pandoc: https://pandoc.org/")
        return False

    try:
        subprocess.run(['wkhtmltopdf', '--version'], capture_output=True, check=True)
        print("✓ wkhtmltopdf found")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("✗ wkhtmltopdf not found. Please install wkhtmltopdf: https://wkhtmltopdf.org/")
        return False

    return True

def convert_to_pdf(input_file, output_file):
    """Convert Markdown file to PDF using pandoc"""
    try:
        cmd = [
            'pandoc',
            str(input_file),
            '-f', 'markdown',
            '-t', 'html',
            '--css', 'pdf-styles.css',
            '--self-contained',
            '-o', str(output_file),
            '--pdf-engine=wkhtmltopdf',
            '--variable', 'geometry:margin=1in',
            '--variable', 'fontsize=11pt',
            '--variable', 'colorlinks=true',
            '--variable', 'linkcolor=blue',
            '--variable', 'urlcolor=blue'
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode == 0:
            print(f"✓ Successfully created {output_file}")
            return True
        else:
            print(f"✗ Failed to create {output_file}")
            print(f"Error: {result.stderr}")
            return False

    except Exception as e:
        print(f"✗ Error converting {input_file}: {e}")
        return False

def create_css_styles():
    """Create CSS styles for PDF generation"""
    css_content = """
/* PDF Styles for Baxter's Hot Rod Tuner Manuals */

body {
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    line-height: 1.6;
    color: #333;
    max-width: none;
    margin: 0;
    padding: 0;
}

h1, h2, h3, h4, h5, h6 {
    color: #2563eb;
    font-weight: 600;
    margin-top: 1.5em;
    margin-bottom: 0.5em;
    page-break-after: avoid;
}

h1 {
    font-size: 2.5em;
    border-bottom: 3px solid #2563eb;
    padding-bottom: 0.3em;
    color: #1e40af;
}

h2 {
    font-size: 2em;
    border-bottom: 2px solid #e5e7eb;
    padding-bottom: 0.2em;
}

h3 {
    font-size: 1.5em;
    color: #374151;
}

code {
    background-color: #f3f4f6;
    padding: 0.2em 0.4em;
    border-radius: 3px;
    font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
    font-size: 0.9em;
}

pre {
    background-color: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    padding: 1em;
    overflow-x: auto;
    font-size: 0.9em;
}

pre code {
    background-color: transparent;
    padding: 0;
}

blockquote {
    border-left: 4px solid #2563eb;
    padding-left: 1em;
    margin-left: 0;
    color: #64748b;
    font-style: italic;
}

table {
    width: 100%;
    border-collapse: collapse;
    margin: 1em 0;
    font-size: 0.9em;
}

th, td {
    border: 1px solid #e5e7eb;
    padding: 0.5em 0.75em;
    text-align: left;
}

th {
    background-color: #f9fafb;
    font-weight: 600;
    color: #374151;
}

tr:nth-child(even) {
    background-color: #f9fafb;
}

ul, ol {
    padding-left: 1.5em;
}

li {
    margin-bottom: 0.25em;
}

a {
    color: #2563eb;
    text-decoration: none;
}

a:hover {
    text-decoration: underline;
}

/* Custom classes for better formatting */
.success {
    color: #059669;
    font-weight: 600;
}

.warning {
    color: #d97706;
    font-weight: 600;
}

.error {
    color: #dc2626;
    font-weight: 600;
}

.info {
    color: #2563eb;
    font-weight: 600;
}

/* Page breaks */
.page-break {
    page-break-before: always;
}

/* Header styling */
.header {
    text-align: center;
    border-bottom: 2px solid #e5e7eb;
    padding-bottom: 1em;
    margin-bottom: 2em;
}

.header h1 {
    margin-bottom: 0.5em;
    color: #1e40af;
}

.header .subtitle {
    color: #6b7280;
    font-size: 1.2em;
    font-weight: 400;
}

/* Footer styling */
.footer {
    text-align: center;
    border-top: 1px solid #e5e7eb;
    padding-top: 1em;
    margin-top: 3em;
    color: #6b7280;
    font-size: 0.9em;
}

/* Code block syntax highlighting */
.hljs-keyword {
    color: #7c3aed;
}

.hljs-string {
    color: #059669;
}

.hljs-number {
    color: #dc2626;
}

.hljs-comment {
    color: #6b7280;
    font-style: italic;
}

/* Table of contents styling */
.toc {
    background-color: #f9fafb;
    border: 1px solid #e5e7eb;
    border-radius: 6px;
    padding: 1.5em;
    margin: 2em 0;
}

.toc h2 {
    margin-top: 0;
    color: #374151;
}

.toc ul {
    list-style-type: none;
    padding-left: 0;
}

.toc li {
    margin-bottom: 0.5em;
}

.toc a {
    color: #374151;
    text-decoration: none;
    display: block;
    padding: 0.25em 0;
}

.toc a:hover {
    color: #2563eb;
}

/* Print-specific styles */
@media print {
    body {
        font-size: 11pt;
    }

    h1 {
        font-size: 24pt;
        page-break-after: avoid;
    }

    h2 {
        font-size: 18pt;
        page-break-after: avoid;
    }

    h3 {
        font-size: 14pt;
        page-break-after: avoid;
    }

    .no-print {
        display: none;
    }
}
"""

    css_file = Path("pdf-styles.css")
    css_file.write_text(css_content, encoding='utf-8')
    print("✓ Created PDF styles file")

def main():
    """Main conversion function"""
    print("Baxter's Hot Rod Tuner Manual PDF Generator")
    print("=" * 50)

    # Check dependencies
    if not check_dependencies():
        print("\nPlease install missing dependencies and try again.")
        sys.exit(1)

    # Create CSS styles
    create_css_styles()

    # Define input and output files
    manuals = [
        {
            'input': Path('../Baxters Self Operating Computer/docs/Hot_Rod_Tuner_SOC_Integration_Manual.md'),
            'output': Path('Hot_Rod_Tuner_SOC_Integration_Manual.pdf'),
            'title': 'SOC Integration Manual'
        },
        {
            'input': Path('Hot_Rod_Tuner_Standalone_Manual.md'),
            'output': Path('Hot_Rod_Tuner_Standalone_Manual.pdf'),
            'title': 'Standalone Manual'
        }
    ]

    success_count = 0

    for manual in manuals:
        print(f"\nConverting {manual['title']}...")
        print(f"Input: {manual['input']}")
        print(f"Output: {manual['output']}")

        if manual['input'].exists():
            if convert_to_pdf(manual['input'], manual['output']):
                success_count += 1
        else:
            print(f"✗ Input file not found: {manual['input']}")

    print(f"\nConversion complete! {success_count}/{len(manuals)} manuals converted successfully.")

    if success_count == len(manuals):
        print("\nPDF manuals created:")
        print("- Hot_Rod_Tuner_SOC_Integration_Manual.pdf")
        print("- Hot_Rod_Tuner_Standalone_Manual.pdf")
        print("\nYou can now distribute these PDF manuals to users.")
    else:
        print("\nSome conversions failed. Please check the error messages above.")

if __name__ == "__main__":
    main()</content>
<parameter name="filePath">c:\Users\Baxter\Desktop\file cabinet\installed apps\Baxters Ai Hot Rod Tuner\generate_pdfs.py