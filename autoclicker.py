import time
import threading
import tkinter as tk
from tkinter import ttk, messagebox
import mss
import pyautogui
import pytesseract
from PIL import Image
import os, sys

# Packaged builds look for Tesseract next to the app; local testing may use PATH.
def configure_tesseract():
    candidates = []
    if getattr(sys, "frozen", False):
        candidates += [
            os.path.join(sys._MEIPASS, "tesseract", "tesseract.exe"),
            os.path.join(os.path.dirname(sys.executable), "tesseract", "tesseract.exe"),
        ]
    for path in candidates:
        if os.path.isfile(path):
            pytesseract.pytesseract.tesseract_cmd = path
            return

configure_tesseract()

MAPPING = {"약": "弱", "중": "中", "강": "強"}
running = False
worker = None
last_seen = set()
cooldown_until = {}

def normalize(s):
    return "".join(ch for ch in s if not ch.isspace())

def scan_screen():
    with mss.mss() as sct:
        shot = sct.grab(sct.monitors[1])
        img = Image.frombytes("RGB", shot.size, shot.rgb)
    # OCR Korean trigger words and Traditional/Simplified Chinese target buttons.
    data = pytesseract.image_to_data(
        img, lang="kor+chi_sim+chi_tra+eng",
        config="--psm 11", output_type=pytesseract.Output.DICT
    )
    words = []
    for i, raw in enumerate(data["text"]):
        word = normalize(raw)
        if not word:
            continue
        try:
            conf = float(data["conf"][i])
        except Exception:
            conf = -1
        if conf < 25:
            continue
        x, y = data["left"][i], data["top"][i]
        w, h = data["width"][i], data["height"][i]
        words.append((word, x, y, w, h))

    # Trigger words can be in multi-character OCR tokens, so check token inclusion.
    present = set()
    for word, x, y, w, h in words:
        for korean in MAPPING:
            if korean in word:
                present.add(korean)

    # Find the corresponding Chinese button by its OCR bounding box.
    found_targets = {}
    for word, x, y, w, h in words:
        for korean, hanja in MAPPING.items():
            if hanja in word:
                found_targets.setdefault(korean, (x + w // 2, y + h // 2))

    return present, found_targets

def loop():
    global running, last_seen
    while running:
        try:
            present, targets = scan_screen()
            # A new appearance is an edge: click once, then wait until Korean label disappears.
            new_words = present - last_seen
            for korean in new_words:
                if korean in targets:
                    x, y = targets[korean]
                    pyautogui.click(x, y)
                    log(f"'{korean}' 감지 → '{MAPPING[korean]}' 클릭 ({x}, {y})")
                else:
                    log(f"'{korean}' 감지했지만 대응 한자 '{MAPPING[korean]}'를 못 찾아 클릭하지 않음")
            last_seen = present
        except Exception as e:
            log("인식 오류: " + str(e))
        time.sleep(0.35)

def log(message):
    try:
        root.after(0, lambda: status.set(message))
    except Exception:
        pass

def start():
    global running, worker, last_seen
    if running:
        return
    try:
        # Verify OCR engine and language data before starting.
        pytesseract.get_tesseract_version()
        langs = pytesseract.get_languages(config="")
        missing = [x for x in ("kor", "chi_sim") if x not in langs]
        if missing:
            messagebox.showerror(
                "OCR 언어 파일 없음",
                "Tesseract 언어 파일이 필요합니다: " + ", ".join(missing) +
                "\n배포 빌드에는 언어 파일을 포함해야 합니다."
            )
            return
    except Exception as e:
        messagebox.showerror(
            "OCR 엔진을 찾을 수 없음",
            "Tesseract OCR 엔진이 필요합니다.\n" + str(e)
        )
        return
    last_seen = set()
    running = True
    worker = threading.Thread(target=loop, daemon=True)
    worker.start()
    status.set("실행 중 — 약/중/강이 새로 나타날 때만 한 번 클릭")
    start_btn.config(state="disabled")
    stop_btn.config(state="normal")

def stop():
    global running
    running = False
    status.set("정지됨")
    start_btn.config(state="normal")
    stop_btn.config(state="disabled")

root = tk.Tk()
root.title("한글 인식 오토클리커")
root.geometry("460x270")
root.resizable(False, False)
frame = ttk.Frame(root, padding=18)
frame.pack(fill="both", expand=True)
ttk.Label(frame, text="한글 인식 오토클리커", font=("Malgun Gothic", 15, "bold")).pack(anchor="w")
ttk.Label(frame, text="약 → 弱   /   중 → 中   /   강 → 強", font=("Malgun Gothic", 12)).pack(anchor="w", pady=(10, 3))
ttk.Label(frame, text="한글이 새로 나타나면 대응하는 한자 버튼을 한 번 클릭합니다.\n한글이 없거나 한자 버튼을 못 찾으면 클릭하지 않습니다.",
          justify="left", wraplength=420).pack(anchor="w", pady=(0, 12))
buttons = ttk.Frame(frame)
buttons.pack(anchor="w")
start_btn = ttk.Button(buttons, text="시작", command=start)
start_btn.pack(side="left", padx=(0, 8))
stop_btn = ttk.Button(buttons, text="정지", command=stop, state="disabled")
stop_btn.pack(side="left")
status = tk.StringVar(value="대기 중")
ttk.Label(frame, textvariable=status, wraplength=420).pack(anchor="w", pady=(15, 0))
ttk.Label(frame, text="주의: OCR이 글자를 잘못 읽으면 오클릭할 수 있습니다. 처음에는 안전한 화면에서 테스트하세요.",
          foreground="#9a4d00", wraplength=420).pack(anchor="w", pady=(10, 0))
root.protocol("WM_DELETE_WINDOW", lambda: (stop(), root.destroy()))
root.mainloop()
