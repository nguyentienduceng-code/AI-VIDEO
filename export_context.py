import os
import sys

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

# Cấu hình các thư mục và đuôi file cần bỏ qua để tránh rác cho AI
IGNORE_DIRS = {".git", "node_modules", "venv", "assets", "__pycache__", "dist", ".vscode", ".idea"}
ALLOWED_EXTENSIONS = {".py", ".jsx", ".js", ".css", ".md", ".json", ".html", ".env.example", ".bat"}

OUTPUT_FILE = "AI_CONTEXT.md"

def generate_tree(dir_path, prefix=""):
    tree_str = ""
    try:
        items = sorted(os.listdir(dir_path))
    except Exception:
        return ""
        
    items = [i for i in items if i not in IGNORE_DIRS and not i.endswith(".lock")]
    
    for i, item in enumerate(items):
        path = os.path.join(dir_path, item)
        is_last = (i == len(items) - 1)
        connector = "└── " if is_last else "├── "
        
        tree_str += f"{prefix}{connector}{item}\n"
        
        if os.path.isdir(path):
            extension_prefix = "    " if is_last else "│   "
            tree_str += generate_tree(path, prefix + extension_prefix)
            
    return tree_str

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(base_dir, OUTPUT_FILE)
    
    with open(output_path, "w", encoding="utf-8") as out:
        out.write("# Bối cảnh mã nguồn - AI Video Maker\n\n")
        out.write("Tài liệu này tổng hợp toàn bộ cấu trúc thư mục và mã nguồn của dự án AI Video Maker. Bạn hãy đọc nó để nắm rõ ngữ cảnh trước khi đưa ra bất kỳ giải pháp hay đoạn mã nào.\n\n")
        
        out.write("## 1. Cấu trúc thư mục\n```text\n")
        out.write("AI-VIDEO-MAKER/\n")
        out.write(generate_tree(base_dir))
        out.write("```\n\n")
        
        out.write("## 2. Toàn bộ Mã Nguồn (Source Code)\n\n")
        
        for root, dirs, files in os.walk(base_dir):
            # Xóa các thư mục cần bỏ qua khỏi cây duyệt
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
            
            for file in sorted(files):
                ext = os.path.splitext(file)[1].lower()
                if ext in ALLOWED_EXTENSIONS and file != OUTPUT_FILE and not file.endswith("package-lock.json"):
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, base_dir)
                    
                    out.write(f"### File: `{rel_path}`\n")
                    out.write(f"```{ext.replace('.', '')}\n")
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            out.write(f.read() + "\n")
                    except Exception as e:
                        out.write(f"// Lỗi khi đọc file: {e}\n")
                    out.write("```\n\n")
                    
    print(f"Đã xuất thành công toàn bộ ngữ cảnh vào file: {output_path}")
    print("Bạn có thể copy nội dung file này để ném cho ChatGPT, Claude, hoặc bất kỳ hệ thống AI nào khác.")

if __name__ == "__main__":
    main()
