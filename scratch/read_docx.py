import zipfile
import xml.etree.ElementTree as ET
import sys
import os

def extract_text_from_docx(docx_path, out_path):
    with zipfile.ZipFile(docx_path) as docx:
        doc_xml = docx.read('word/document.xml')
        root = ET.fromstring(doc_xml)
        paragraphs = []
        for elem in root.iter():
            if elem.tag.endswith('}p') or elem.tag == 'p':
                p_text = []
                for child in elem.iter():
                    if child.tag.endswith('}t') or child.tag == 't':
                        if child.text:
                            p_text.append(child.text)
                paragraphs.append("".join(p_text))
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(paragraphs))
    print(f"Done: {out_path}")

extract_text_from_docx(sys.argv[1], sys.argv[2])
