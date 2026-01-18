# Baxter's AI Hot Rod Tuner - Documentation

This directory contains comprehensive user manuals for Baxter's AI Hot Rod Tuner in two versions:

## 📚 Available Manuals

### 1. SOC Integration Manual
**File**: `Hot_Rod_Tuner_SOC_Integration_Manual.md` / `Hot_Rod_Tuner_SOC_Integration_Manual.pdf`

**Purpose**: Complete guide for users who want to use Hot Rod Tuner within Baxter's Self Operating Computer (SOC) interface.

**Contents**:
- SOC integration setup and configuration
- Thermal management interface walkthrough
- Performance tuning within SOC
- System monitoring and logging
- Configuration management
- Troubleshooting guide

**Target Audience**: SOC users who want integrated thermal and performance management.

### 2. Standalone Manual
**File**: `Hot_Rod_Tuner_Standalone_Manual.md` / `Hot_Rod_Tuner_Standalone_Manual.pdf`

**Purpose**: Comprehensive guide for running Hot Rod Tuner as an independent service.

**Contents**:
- Standalone installation and setup
- Core features and architecture
- Telemetry collection and monitoring
- Policy engine configuration
- Job scheduling and management
- Thermal management system
- Sound system configuration
- API reference and integration
- Advanced usage and customization

**Target Audience**: System administrators, developers, and power users who want to run Hot Rod Tuner independently.

## 🛠️ PDF Generation

### Prerequisites

To generate PDF versions of the manuals, you need:

1. **Python 3.8+**
2. **pandoc** - Universal document converter
   - Download: https://pandoc.org/installing.html
3. **wkhtmltopdf** - HTML to PDF converter
   - Download: https://wkhtmltopdf.org/downloads.html

### Installation

```bash
# Install Python dependencies
pip install pypandoc

# Install pandoc (choose your platform)
# Windows: Use installer from pandoc.org
# macOS: brew install pandoc
# Linux: sudo apt-get install pandoc

# Install wkhtmltopdf (choose your platform)
# Windows: Use installer from wkhtmltopdf.org
# macOS: brew install wkhtmltopdf
# Linux: sudo apt-get install wkhtmltopdf
```

### Generate PDFs

Run the PDF generation script:

```bash
python generate_pdfs.py
```

This will create:
- `Hot_Rod_Tuner_SOC_Integration_Manual.pdf`
- `Hot_Rod_Tuner_Standalone_Manual.pdf`

## 📖 Manual Features

Both manuals include:

- **Comprehensive Setup Instructions**: Step-by-step installation and configuration
- **Feature Documentation**: Detailed explanations of all Hot Rod Tuner capabilities
- **API Reference**: Complete API documentation with examples
- **Troubleshooting Guide**: Common issues and solutions
- **Best Practices**: Recommendations for optimal configuration
- **Integration Examples**: Code samples for custom integrations

## 🎯 When to Use Each Manual

### Use SOC Integration Manual When:
- You want to use Hot Rod Tuner within SOC interface
- You need integrated thermal management in SOC
- You're managing AI workloads through SOC
- You want unified monitoring and control

### Use Standalone Manual When:
- You want to run Hot Rod Tuner independently
- You're building custom integrations
- You need advanced configuration options
- You're deploying in enterprise environments
- You want to use Hot Rod as a service for multiple applications

## 📄 Manual Formats

### Markdown (.md)
- **Editable**: Can be modified and version controlled
- **GitHub Compatible**: Renders well on GitHub and GitLab
- **Searchable**: Easy to search and navigate
- **Lightweight**: Small file size

### PDF (.pdf)
- **Professional**: Print-ready format
- **Portable**: Universal document format
- **Archival**: Perfect for distribution and documentation
- **Consistent**: Looks the same on all devices

## 🔄 Updating Manuals

When updating the manuals:

1. Edit the `.md` files with your changes
2. Test the changes by viewing on GitHub or local Markdown viewer
3. Regenerate PDFs using `python generate_pdfs.py`
4. Commit both `.md` and `.pdf` files to version control

## 📞 Support

For questions about the manuals or Hot Rod Tuner:

- Check the troubleshooting sections in each manual
- Review the API reference for integration questions
- Contact Baxter's technical support team

---

**Version**: 1.0
**Date**: January 17, 2026
**Author**: Baxter's Development Team</content>
<parameter name="filePath">c:\Users\Baxter\Desktop\file cabinet\installed apps\Baxters Ai Hot Rod Tuner\README_Documentation.md