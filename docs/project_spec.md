# AI-Powered UX Research Data Structuring Pipeline

## Overview
This project is an end-to-end AI system that converts unstructured text data from PDFs or text files into structured CSV datasets. It focuses on reliability, modularity, and real-world usability.

## Goals
- Transform messy text into structured data
- Support user-defined schemas
- Provide insights (themes, keywords)
- Operate using lightweight local models

## Core Features
- File upload (PDF, text)
- Schema builder (dynamic fields)
- Entry segmentation
- LLM-based extraction
- Validation + retry
- Confidence scoring
- CSV export
- Insights dashboard

## Architecture
PDF/Text → Extraction → Segmentation → LLM → Validation → CSV → Insights

## Tech Stack
- Python
- Streamlit
- Ollama (local LLM)
- PyMuPDF / pdfplumber
- Pandas
- sentence-transformers (optional)

## Output Schema
id, raw_text, <user_fields>, confidence

## Key Principles
- Reliability over complexity
- Modular design
- Human-in-the-loop support
