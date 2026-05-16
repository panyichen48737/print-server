"""PDF 渲染工具 — N-up 拼版"""

import tempfile

import fitz


def nup_compose(input_pdf: str, pages_per_sheet: int = 2) -> str:
    """将 PDF 页面按 N-up 拼版，返回临时 PDF 路径。（调用者负责 cleanup）"""
    doc = fitz.open(input_pdf)
    total = len(doc)
    if total <= 1:
        doc.close()
        return input_pdf

    grid_map = {1: (1, 1), 2: (1, 2), 4: (2, 2), 6: (2, 3), 8: (2, 4), 16: (4, 4)}
    cols, rows = grid_map.get(pages_per_sheet, (1, 2))

    # A4 尺寸 (points)
    page_w, page_h = 595, 842
    # 动态缩放：高密度拼版使用更高分辨率确保文字可读
    scale = max(0.3, 2.0 / max(cols, rows))

    output_doc = fitz.open()

    for i in range(0, total, pages_per_sheet):
        page = output_doc.new_page(width=page_w, height=page_h)

        for j in range(pages_per_sheet):
            idx = i + j
            if idx >= total:
                break

            col = j % cols
            row_idx = j // cols
            cell_w = page_w / cols
            cell_h = page_h / rows

            x0 = col * cell_w
            y0 = row_idx * cell_h

            mat = fitz.Matrix(scale, scale)
            pix = doc[idx].get_pixmap(matrix=mat)

            # Calculate centered position within cell
            img_w = pix.width
            img_h = pix.height

            if img_w <= 0 or img_h <= 0:
                continue

            cell_scale = min(cell_w / img_w, cell_h / img_h) * 0.95
            final_w = img_w * cell_scale
            final_h = img_h * cell_scale
            cx = x0 + (cell_w - final_w) / 2
            cy = y0 + (cell_h - final_h) / 2

            page.insert_image(
                fitz.Rect(cx, cy, cx + final_w, cy + final_h),
                stream=pix.tobytes('png'),
            )

    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
        out_path = tmp.name
    output_doc.save(out_path)
    output_doc.close()
    doc.close()
    return out_path
