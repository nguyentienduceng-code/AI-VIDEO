import os
import sys
import argparse
from pypdf import PdfReader, PdfWriter

def split_pdf(input_path, chunk_size):
    if not os.path.exists(input_path):
        print(f"❌ Lỗi: Không tìm thấy file {input_path}")
        return

    reader = PdfReader(input_path)
    total_pages = len(reader.pages)
    
    base_name = os.path.splitext(os.path.basename(input_path))[0]
    out_dir = os.path.join(os.path.dirname(input_path) or ".", f"{base_name}_chapters")
    os.makedirs(out_dir, exist_ok=True)

    print(f"📚 Đang xử lý: {base_name}.pdf ({total_pages} trang)")
    print(f"✂️ Cắt mỗi {chunk_size} trang thành 1 file (tương đương 1 chương)...")

    for i in range(0, total_pages, chunk_size):
        writer = PdfWriter()
        start_page = i
        end_page = min(i + chunk_size, total_pages)
        
        for j in range(start_page, end_page):
            writer.add_page(reader.pages[j])
            
        part_num = (i // chunk_size) + 1
        out_filename = f"{base_name}_Phan_{part_num:02d}.pdf"
        out_filepath = os.path.join(out_dir, out_filename)
        
        with open(out_filepath, "wb") as f:
            writer.write(f)
            
        print(f"✅ Đã tạo: {out_filename} (trang {start_page+1} đến {end_page})")

    print(f"\n🎉 XONG! Các file đã được lưu trong thư mục: {out_dir}")
    print("👉 Bây giờ anh/chị chỉ cần kéo toàn bộ thư mục này thả vào Notebook LM!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Công cụ tự động cắt PDF")
    parser.add_argument("pdf_file", help="Đường dẫn đến file PDF (Ví dụ: book.pdf)")
    parser.add_argument("--pages", type=int, default=15, help="Số trang mỗi file (Mặc định: 15)")
    args = parser.parse_args()
    
    split_pdf(args.pdf_file, args.pages)
