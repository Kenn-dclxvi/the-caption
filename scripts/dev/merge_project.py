import os
import sys
import ast
import re
from datetime import datetime
from typing import Dict, Any, List, Optional

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)
from src.config.settings import VERSION

_TIMESTAMP = datetime.now().strftime('%Y%m%d%H%M%S')
OUTPUT_FILENAME = f"Project_Full_v{VERSION}_{_TIMESTAMP}.txt"

EXCLUDE_DIRS = {
    "__pycache__", ".git", ".idea", ".vscode", "venv", ".venv",
    "data", "logs", "auth", "archive", "node_modules"
}

EXCLUDE_FILES = {
    ".env", ".env.bak", ".env.enc", "secret.key", ".DS_Store", ".gitignore", "data*.tar.gz"
}

LAYER_MAP = {
    "modules": "LOGIC",
    "common": "INFRA",
    "config": "INFRA",
    "templates": "VIEW",
    "static": "VIEW",
    "docs": "DOC",
    "tools": "TOOL"
}

class MetadataExtractor:
    __LEGACY_REV_RE = re.compile(r"Rev\.\s*(\d+)")

    @classmethod
    def __get_revision(cls, content: str) -> str:
        rev_match = cls.__LEGACY_REV_RE.search(content)
        if rev_match:
            return rev_match.group(1)
        return "0"

    @staticmethod
    def __get_layer(path: str) -> str:
        parts = path.split('/')
        for key, layer in LAYER_MAP.items():
            if key in parts:
                return layer
        return "UNKNOWN"

    @staticmethod
    def __get_imports(content: str) -> List[str]:
        imports = set()
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.add(alias.name.split('.')[0])
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.add(node.module.split('.')[0])
        except (SyntaxError, ValueError, Exception):
            pass
        return sorted(list(imports))

    @classmethod
    def extract(cls, path: str, content: str) -> Dict[str, Any]:
        return {
            "rev": cls.__get_revision(content),
            "layer": cls.__get_layer(path),
            "deps": cls.__get_imports(content),
            "original_path": path
        }

def execute_merge() -> None:
    file_count = 0
    extractor = MetadataExtractor()
    target_exts = {".py", ".md", ".txt", ".yaml", ".json"}

    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    os.chdir(root_dir)

    with open(OUTPUT_FILENAME, "w", encoding="utf-8") as outfile:
        outfile.write("<project_metadata>\n")
        outfile.write("Protocol: XML-Tag Case 1 Rev.2\n")
        outfile.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        outfile.write("Description: Enhanced source code package with Output-Exclusion logic.\n")
        outfile.write("</project_metadata>\n\n")

        for root, dirs, files in os.walk("."):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]

            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if (file in EXCLUDE_FILES or 
                    ext not in target_exts or 
                    file.startswith("Project_Full")):
                    continue
                
                file_path = os.path.join(root, file)
                normalized_path = file_path.replace(os.sep, '/').lstrip('./')
                
                try:
                    with open(file_path, "r", encoding="utf-8") as infile:
                        content = infile.read()
                        
                        meta = extractor.extract(normalized_path, content)
                        
                        display_path = meta["original_path"] if meta["original_path"] else normalized_path
                        
                        outfile.write(f'<file path="{display_path}" layer="{meta["layer"]}" rev="{meta["rev"]}">\n')
                        
                        if meta["deps"]:
                            outfile.write("<dependencies>\n")
                            for dep in meta["deps"]:
                                outfile.write(f"- {dep}\n")
                            outfile.write("</dependencies>\n")
                            
                        outfile.write("<content>\n")
                        outfile.write(content)
                        if not content.endswith('\n'):
                            outfile.write('\n')
                        outfile.write("</content>\n")
                        outfile.write("</file>\n\n")

                        file_count += 1
                except Exception:
                    pass

    print(f"[Success] Project merged into {OUTPUT_FILENAME}")
    print(f"[Stats] Total Files: {file_count}")

if __name__ == "__main__":
    execute_merge()
