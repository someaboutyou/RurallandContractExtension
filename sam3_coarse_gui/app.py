import json
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import cv2
import numpy as np
import tkinter as tk
from PIL import Image, ImageTk
from tkinter import filedialog, messagebox, ttk


THIS_DIR = Path(__file__).resolve().parent
CONFIG_PATH = THIS_DIR / "label_mapping.json"
SAM31_CHECKPOINT = Path(r"E:\Work\AIVerification\sam3.1\sam3.1_multiplex.pt")
SAM31_INFER_SCRIPT = Path(r"E:\Work\AIVerification\sam31_depth_anything_infer.py")
SAM31_OUTPUT_ROOT = Path(r"E:\Work\AIVerification\outputs\sam31_depth_anything")
SUPPORTED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
PALETTE = np.array(
    [
        [255, 99, 71],
        [65, 105, 225],
        [60, 179, 113],
        [255, 215, 0],
        [186, 85, 211],
        [255, 140, 0],
        [0, 191, 255],
        [154, 205, 50],
    ],
    dtype=np.uint8,
)


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def slugify(text: str) -> str:
    safe = []
    for char in text.strip():
        if char.isalnum() or char in "_-":
            safe.append(char)
        else:
            safe.append("_")
    joined = "".join(safe).strip("_")
    return joined or "prompt"


def resize_mask(mask: np.ndarray, height: int, width: int) -> np.ndarray:
    if mask.shape == (height, width):
        return mask.astype(bool)
    return (
        cv2.resize(mask.astype(np.float32), (width, height), interpolation=cv2.INTER_NEAREST)
        > 0.5
    )


def create_single_frame_folder(image_path: Path) -> Path:
    temp_root = Path(tempfile.mkdtemp(prefix="sam3_gui_"))
    frame_path = temp_root / "00000.jpg"
    image = cv2.imread(str(image_path))
    if image is None:
        shutil.rmtree(temp_root, ignore_errors=True)
        raise RuntimeError(f"Failed to read image: {image_path}")
    cv2.imwrite(str(frame_path), image)
    return temp_root


def build_overlay(image_bgr: np.ndarray, outputs: dict, prompt: str) -> tuple[np.ndarray, dict]:
    overlay = image_bgr.copy()
    height, width = image_bgr.shape[:2]
    masks = outputs.get("out_binary_masks", np.zeros((0, height, width), dtype=bool))
    boxes = outputs.get("out_boxes_xywh", np.zeros((0, 4), dtype=np.float32))
    scores = outputs.get("out_probs", [None] * len(masks))
    obj_ids = outputs.get("out_obj_ids", np.arange(len(masks)))
    union_mask = np.zeros((height, width), dtype=bool)
    objects = []

    for idx in range(len(masks)):
        obj_id = int(obj_ids[idx])
        color = PALETTE[obj_id % len(PALETTE)].tolist()
        mask = resize_mask(masks[idx], height, width)
        union_mask |= mask

        color_img = np.zeros_like(overlay)
        color_img[mask] = color
        overlay = np.where(color_img > 0, overlay * 0.45 + color_img * 0.55, overlay)

        x, y, w, h = boxes[idx]
        x1 = int(round(x * width))
        y1 = int(round(y * height))
        x2 = int(round((x + w) * width))
        y2 = int(round((y + h) * height))
        cv2.rectangle(overlay, (x1, y1), (x2, y2), color, 2)

        score = None if scores[idx] is None else float(scores[idx])
        label = f"{prompt} | id={obj_id}"
        if score is not None:
            label += f" | p={score:.2f}"
        cv2.putText(
            overlay,
            label,
            (x1, max(22, y1 - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            color,
            2,
            cv2.LINE_AA,
        )

        objects.append(
            {
                "obj_id": obj_id,
                "score": score,
                "bbox_xyxy_px": [x1, y1, x2, y2],
                "mask_area_px": int(mask.sum()),
                "mask_area_ratio": float(mask.mean()),
            }
        )

    if not objects:
        cv2.putText(
            overlay,
            f"No masks found for: {prompt}",
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (0, 0, 255),
            2,
            cv2.LINE_AA,
        )

    summary = {
        "num_masks": len(objects),
        "union_mask_area_ratio": float(union_mask.mean()),
        "objects": objects,
    }
    return overlay.astype(np.uint8), summary


class Sam3CoarseSegmenter:
    def __init__(self, checkpoint_path: Path):
        self.checkpoint_path = checkpoint_path

    def segment(self, image_path: Path, prompt: str, threshold: float) -> tuple[np.ndarray, np.ndarray, dict]:
        sample_name = f"{image_path.stem}_{slugify(prompt)}"
        outdir = SAM31_OUTPUT_ROOT / sample_name
        command = [
            sys.executable,
            str(SAM31_INFER_SCRIPT),
            "--image",
            str(image_path),
            "--prompt",
            prompt,
            "--sam-checkpoint",
            str(self.checkpoint_path),
            "--sam-threshold",
            str(threshold),
        ]
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                "SAM3 粗分割脚本执行失败。\n"
                f"命令: {' '.join(command)}\n"
                f"stdout:\n{result.stdout}\n"
                f"stderr:\n{result.stderr}"
            )

        overlay_path = outdir / "sam31_overlay.png"
        summary_path = outdir / "summary.json"
        image_bgr = cv2.imread(str(image_path))
        overlay_bgr = cv2.imread(str(overlay_path))
        if image_bgr is None:
            raise RuntimeError(f"Failed to read image: {image_path}")
        if overlay_bgr is None:
            raise RuntimeError(f"Failed to read overlay image: {overlay_path}")
        if not summary_path.exists():
            raise RuntimeError(f"Summary file not found: {summary_path}")
        with open(summary_path, "r", encoding="utf-8") as f:
            summary = json.load(f)
        return image_bgr, overlay_bgr, summary


class Sam3CoarseGui:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("SAM3 粗分割工具")
        self.root.geometry("1660x940")

        self.label_mapping = self._load_mapping()
        self.leaf_items = {}
        self.image_paths = []
        self.current_image_path = None
        self.segmenter = Sam3CoarseSegmenter(SAM31_CHECKPOINT)
        self.result_queue = queue.Queue()
        self.worker_running = False
        self.current_original_photo = None
        self.current_overlay_photo = None

        self._build_ui()
        self._populate_mapping_tree()
        self.root.after(200, self._poll_worker_queue)

    def _load_mapping(self):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    def _build_ui(self):
        main = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main.pack(fill=tk.BOTH, expand=True)

        control = ttk.Frame(main, padding=10)
        viewer = ttk.Frame(main, padding=10)
        main.add(control, weight=1)
        main.add(viewer, weight=3)

        path_frame = ttk.LabelFrame(control, text="输入")
        path_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Button(path_frame, text="打开图片", command=self.open_image).pack(fill=tk.X, padx=8, pady=(8, 4))
        ttk.Button(path_frame, text="打开文件夹", command=self.open_folder).pack(fill=tk.X, padx=8, pady=4)
        self.path_var = tk.StringVar(value="未选择图片")
        ttk.Label(path_frame, textvariable=self.path_var, wraplength=320).pack(fill=tk.X, padx=8, pady=(4, 8))

        list_frame = ttk.LabelFrame(control, text="图片列表")
        list_frame.pack(fill=tk.BOTH, expand=False, pady=(0, 10))
        self.image_listbox = tk.Listbox(list_frame, height=10)
        self.image_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0), pady=8)
        self.image_listbox.bind("<<ListboxSelect>>", self.on_image_select)
        list_scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.image_listbox.yview)
        list_scroll.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 8), pady=8)
        self.image_listbox.configure(yscrollcommand=list_scroll.set)

        mapping_frame = ttk.LabelFrame(control, text="业务标签 / 模型标签 对照")
        mapping_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        self.mapping_tree = ttk.Treeview(
            mapping_frame,
            columns=("business", "model", "prompt"),
            show="tree headings",
            height=18,
        )
        self.mapping_tree.heading("#0", text="一级类")
        self.mapping_tree.heading("business", text="业务标签")
        self.mapping_tree.heading("model", text="模型标签")
        self.mapping_tree.heading("prompt", text="SAM 提示词")
        self.mapping_tree.column("#0", width=90, anchor=tk.W)
        self.mapping_tree.column("business", width=120, anchor=tk.W)
        self.mapping_tree.column("model", width=130, anchor=tk.W)
        self.mapping_tree.column("prompt", width=120, anchor=tk.W)
        self.mapping_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0), pady=8)
        self.mapping_tree.bind("<<TreeviewSelect>>", self.on_mapping_select)
        mapping_scroll = ttk.Scrollbar(mapping_frame, orient=tk.VERTICAL, command=self.mapping_tree.yview)
        mapping_scroll.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 8), pady=8)
        self.mapping_tree.configure(yscrollcommand=mapping_scroll.set)

        action_frame = ttk.LabelFrame(control, text="分割")
        action_frame.pack(fill=tk.X)
        threshold_row = ttk.Frame(action_frame)
        threshold_row.pack(fill=tk.X, padx=8, pady=(8, 4))
        ttk.Label(threshold_row, text="阈值").pack(side=tk.LEFT)
        self.threshold_var = tk.StringVar(value="0.50")
        ttk.Entry(threshold_row, textvariable=self.threshold_var, width=8).pack(side=tk.LEFT, padx=(8, 0))
        self.segment_button = ttk.Button(action_frame, text="开始粗分割", command=self.segment_current)
        self.segment_button.pack(fill=tk.X, padx=8, pady=8)
        self.selection_var = tk.StringVar(value="当前未选择业务标签")
        ttk.Label(action_frame, textvariable=self.selection_var, wraplength=320).pack(fill=tk.X, padx=8, pady=(0, 8))

        status_frame = ttk.LabelFrame(control, text="状态")
        status_frame.pack(fill=tk.BOTH, expand=False, pady=(10, 0))
        self.status_text = tk.Text(status_frame, height=8, wrap=tk.WORD)
        self.status_text.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.status_text.insert("1.0", "程序已启动。\n")
        self.status_text.configure(state=tk.DISABLED)

        viewer_row = ttk.Frame(viewer)
        viewer_row.pack(fill=tk.BOTH, expand=True)

        original_frame = ttk.LabelFrame(viewer_row, text="原始图片")
        original_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        self.original_image_label = ttk.Label(original_frame, anchor=tk.CENTER)
        self.original_image_label.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        overlay_frame = ttk.LabelFrame(viewer_row, text="SAM3 粗分割结果")
        overlay_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0))
        self.overlay_image_label = ttk.Label(overlay_frame, anchor=tk.CENTER)
        self.overlay_image_label.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

    def _populate_mapping_tree(self):
        self.mapping_tree.delete(*self.mapping_tree.get_children())
        self.leaf_items.clear()

        leaf_index = 0
        for group in self.label_mapping:
            parent_id = self.mapping_tree.insert("", tk.END, text=group["一级类"], open=True)
            for item in group["items"]:
                leaf_id = f"leaf_{leaf_index}"
                self.mapping_tree.insert(
                    parent_id,
                    tk.END,
                    iid=leaf_id,
                    text="",
                    values=(item["业务标签"], item["模型标签"], item["sam_prompt"]),
                )
                self.leaf_items[leaf_id] = {
                    "一级类": group["一级类"],
                    "业务标签": item["业务标签"],
                    "模型标签": item["模型标签"],
                    "sam_prompt": item["sam_prompt"],
                }
                leaf_index += 1

    def append_status(self, message: str):
        self.status_text.configure(state=tk.NORMAL)
        self.status_text.insert(tk.END, message + "\n")
        self.status_text.see(tk.END)
        self.status_text.configure(state=tk.DISABLED)

    def open_image(self):
        file_path = filedialog.askopenfilename(
            title="选择图片",
            filetypes=[("Image Files", "*.jpg *.jpeg *.png *.bmp *.tif *.tiff *.webp")],
        )
        if not file_path:
            return
        self.image_paths = [Path(file_path)]
        self._refresh_image_list()
        self._set_current_image(self.image_paths[0])

    def open_folder(self):
        folder_path = filedialog.askdirectory(title="选择图片文件夹")
        if not folder_path:
            return
        folder = Path(folder_path)
        self.image_paths = sorted([p for p in folder.iterdir() if p.suffix.lower() in SUPPORTED_IMAGE_EXTS])
        if not self.image_paths:
            messagebox.showwarning("没有图片", "所选文件夹中没有可识别的图片文件。")
            return
        self._refresh_image_list()
        self._set_current_image(self.image_paths[0])

    def _refresh_image_list(self):
        self.image_listbox.delete(0, tk.END)
        for path in self.image_paths:
            self.image_listbox.insert(tk.END, path.name)
        if self.image_paths:
            self.image_listbox.selection_clear(0, tk.END)
            self.image_listbox.selection_set(0)
            self.image_listbox.activate(0)

    def _set_current_image(self, image_path: Path):
        self.current_image_path = image_path
        self.path_var.set(str(image_path))
        self._show_image(image_path, self.original_image_label, is_original=True)
        self.overlay_image_label.configure(image="", text="")
        self.current_overlay_photo = None
        self.append_status(f"已载入图片: {image_path.name}")

    def on_image_select(self, _event=None):
        selection = self.image_listbox.curselection()
        if not selection:
            return
        index = selection[0]
        if 0 <= index < len(self.image_paths):
            self._set_current_image(self.image_paths[index])

    def on_mapping_select(self, _event=None):
        selection = self.mapping_tree.selection()
        if not selection:
            return
        item_id = selection[0]
        if item_id not in self.leaf_items:
            return
        item = self.leaf_items[item_id]
        self.selection_var.set(
            f"业务标签: {item['业务标签']} | 模型标签: {item['模型标签']} | Prompt: {item['sam_prompt']}"
        )

    def get_selected_mapping(self):
        selection = self.mapping_tree.selection()
        if not selection:
            return None
        item_id = selection[0]
        return self.leaf_items.get(item_id)

    def segment_current(self):
        if self.worker_running:
            messagebox.showinfo("处理中", "当前还有分割任务在运行，请稍候。")
            return
        if self.current_image_path is None:
            messagebox.showwarning("未选择图片", "请先打开一张图片或一个文件夹。")
            return
        mapping_item = self.get_selected_mapping()
        if mapping_item is None:
            messagebox.showwarning("未选择标签", "请先在左侧选择一个业务标签。")
            return
        try:
            threshold = float(self.threshold_var.get())
        except ValueError:
            messagebox.showerror("阈值错误", "阈值必须是数字，例如 0.5。")
            return

        self.worker_running = True
        self.segment_button.configure(state=tk.DISABLED)
        self.append_status(
            f"开始分割: {self.current_image_path.name} | 业务标签={mapping_item['业务标签']} | Prompt={mapping_item['sam_prompt']}"
        )

        worker = threading.Thread(
            target=self._segment_worker,
            args=(self.current_image_path, mapping_item, threshold),
            daemon=True,
        )
        worker.start()

    def _segment_worker(self, image_path: Path, mapping_item: dict, threshold: float):
        try:
            original_bgr, overlay_bgr, summary = self.segmenter.segment(
                image_path=image_path,
                prompt=mapping_item["sam_prompt"],
                threshold=threshold,
            )
            self.result_queue.put(
                {
                    "ok": True,
                    "image_path": image_path,
                    "mapping_item": mapping_item,
                    "original_bgr": original_bgr,
                    "overlay_bgr": overlay_bgr,
                    "summary": summary,
                }
            )
        except Exception as exc:
            self.result_queue.put(
                {
                    "ok": False,
                    "image_path": image_path,
                    "mapping_item": mapping_item,
                    "error": str(exc),
                }
            )

    def _poll_worker_queue(self):
        try:
            while True:
                message = self.result_queue.get_nowait()
                self._handle_worker_result(message)
        except queue.Empty:
            pass
        self.root.after(200, self._poll_worker_queue)

    def _handle_worker_result(self, message: dict):
        self.worker_running = False
        self.segment_button.configure(state=tk.NORMAL)

        if not message["ok"]:
            self.append_status(
                f"分割失败: {message['image_path'].name} | {message['mapping_item']['业务标签']} | {message['error']}"
            )
            messagebox.showerror("分割失败", message["error"])
            return

        self._show_bgr_array(message["original_bgr"], self.original_image_label, is_original=True)
        self._show_bgr_array(message["overlay_bgr"], self.overlay_image_label, is_original=False)
        summary = message["summary"]
        self.append_status(
            "分割完成: "
            f"{message['image_path'].name} | 业务标签={message['mapping_item']['业务标签']} | "
            f"模型标签={message['mapping_item']['模型标签']} | Prompt={message['mapping_item']['sam_prompt']} | "
            f"mask 数量={summary['num_masks']} | 联合面积占比={summary['union_mask_area_ratio']:.4f}"
        )

    def _show_image(self, image_path: Path, widget: ttk.Label, is_original: bool):
        image_bgr = cv2.imread(str(image_path))
        if image_bgr is None:
            raise RuntimeError(f"Failed to read image: {image_path}")
        self._show_bgr_array(image_bgr, widget, is_original=is_original)

    def _show_bgr_array(self, image_bgr: np.ndarray, widget: ttk.Label, is_original: bool):
        rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(rgb)

        max_width = 760
        max_height = 820
        scale = min(max_width / image.width, max_height / image.height, 1.0)
        display_size = (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
        image = image.resize(display_size, Image.Resampling.LANCZOS)

        photo = ImageTk.PhotoImage(image)
        widget.configure(image=photo)
        widget.image = photo

        if is_original:
            self.current_original_photo = photo
        else:
            self.current_overlay_photo = photo


def main():
    if not SAM31_CHECKPOINT.exists():
        raise FileNotFoundError(f"SAM 3.1 checkpoint not found: {SAM31_CHECKPOINT}")
    if not SAM31_INFER_SCRIPT.exists():
        raise FileNotFoundError(f"SAM 3.1 inference script not found: {SAM31_INFER_SCRIPT}")
    ensure_dir(THIS_DIR)

    root = tk.Tk()
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass
    Sam3CoarseGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
