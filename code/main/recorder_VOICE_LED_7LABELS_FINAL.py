import tkinter as tk
from tkinter import ttk, messagebox
import serial
import serial.tools.list_ports
import threading
import os
import time
import re
import winsound


# ============================================================
# CẤU HÌNH
# ============================================================

BAUDRATE = 921600

SAMPLE_RATE = 16000
BITS_PER_SAMPLE = 16
CHANNELS = 1
RECORD_SECONDS = 2

AUDIO_BYTES = SAMPLE_RATE * RECORD_SECONDS * CHANNELS * BITS_PER_SAMPLE // 8
WAV_HEADER_SIZE = 44

DATASET_FOLDER = "dataset"

CLASSES = [
    "bat_xanh",
    "bat_do",
    "bat_vang",
    "tat_do",
    "tat_xanh",
    "tat_vang",
    "unknown"
]


# ============================================================
# BIẾN TOÀN CỤC
# ============================================================

ser = None
busy = False
worker_thread = None
last_wav_path = None

AI_LABELS = [
    "bat_xanh",
    "bat_do",
    "bat_vang",
    "tat_do",
    "tat_xanh",
    "tat_vang",
    "unknown"
]


# ============================================================
# TÌM COM PORT
# ============================================================

def get_com_ports():
    ports = serial.tools.list_ports.comports()
    result = []

    for port in ports:
        result.append(port.device)

    return result


def refresh_ports():
    ports = get_com_ports()
    combo_port["values"] = ports

    if ports:
        combo_port.current(0)


# ============================================================
# TÌM SỐ FILE TIẾP THEO
# ============================================================

def get_next_number(class_name):
    folder = os.path.join(DATASET_FOLDER, class_name)
    os.makedirs(folder, exist_ok=True)

    max_number = 0

    for filename in os.listdir(folder):
        if not filename.lower().endswith(".wav"):
            continue

        name = os.path.splitext(filename)[0]
        parts = name.rsplit("_", 1)      # <-- phải là rsplit, không phải split

        if len(parts) == 2:
            try:
                number = int(parts[-1])
                if number > max_number:
                    max_number = number
            except ValueError:
                pass

    return max_number + 1


# ============================================================
# ĐỌC ĐỦ N BYTE
# ============================================================

def read_exact(number_of_bytes):
    data = bytearray()

    while len(data) < number_of_bytes:
        if ser is None:
            raise Exception("Serial chưa kết nối.")

        remaining = number_of_bytes - len(data)
        chunk = ser.read(min(4096, remaining))

        if not chunk:
            continue

        data.extend(chunk)

    return bytes(data)


# ============================================================
# ĐỌC 1 DÒNG TEXT TỪ SERIAL
# ============================================================

def read_line_blocking(timeout_seconds=10.0):
    deadline = time.monotonic() + timeout_seconds

    while time.monotonic() < deadline:
        if ser is None or not ser.is_open:
            raise Exception("Serial chưa kết nối.")

        line = ser.readline()

        if not line:
            continue

        try:
            text = line.decode("utf-8", errors="ignore").strip()
        except Exception:
            text = ""

        if text:
            return text

    raise TimeoutError(f"Hết thời gian chờ phản hồi serial sau {timeout_seconds} giây.")


def wait_for_message(expected_prefixes, timeout_seconds=10.0):
    deadline = time.monotonic() + timeout_seconds

    while time.monotonic() < deadline:
        if ser is None or not ser.is_open:
            raise Exception("Serial chưa kết nối.")

        line = ser.readline()

        if not line:
            continue

        try:
            text = line.decode("utf-8", errors="ignore").strip()
        except Exception:
            text = ""

        if not text:
            continue

        for prefix in expected_prefixes:
            if text.startswith(prefix):
                return text

        # Bỏ qua các dòng rác hoặc startup message không cần thiết.
        if text.startswith("ESP32") or text.startswith("INMP441") or text.startswith("I2S"):
            continue

        if text.startswith("Voice recorder ready"):
            continue

        if text.startswith("================================"):
            continue

        # Nếu không khớp với token mong đợi, vẫn hiện log để dễ debug.
        add_log(f"[ignored] {text}")

    raise TimeoutError(f"Không nhận được phản hồi mong đợi: {expected_prefixes}")


# ============================================================
# KIỂM TRA WAV HEADER
# ============================================================

def validate_wav_header(header):
    if len(header) != 44:
        return False

    if header[0:4] != b"RIFF":
        return False

    if header[8:12] != b"WAVE":
        return False

    if header[12:16] != b"fmt ":
        return False

    if header[36:40] != b"data":
        return False

    return True


# ============================================================
# CẬP NHẬT GIAO DIỆN (an toàn khi gọi từ thread khác)
# ============================================================

def set_status(text):
    root.after(0, lambda: status_var.set(text))


def set_file_count(text):
    root.after(0, lambda: file_count_var.set(text))


def add_log(text):
    def update():
        text_log.config(state="normal")
        text_log.insert(tk.END, text + "\n")
        text_log.see(tk.END)
        text_log.config(state="disabled")

    root.after(0, update)


def set_buttons_enabled(enabled):
    def update():
        state = "normal" if enabled else "disabled"
        btn_start.config(state=state)
        btn_open.config(state=state)
        btn_play.config(state=state)
        btn_stop.config(state=state)

    root.after(0, update)


# ============================================================
# EDGE IMPULSE RESULT + NGHE LẠI WAV
# ============================================================

def reset_ai_display():
    def update():
        for label in AI_LABELS:
            score_vars[label].set(f"{label}: 0.00%")
        prediction_var.set("Dự đoán: ---")
        led_action_var.set("LED: ---")

    root.after(0, update)


def parse_ai_line(line):
    # Đúng format: bat_xanh: 98.23
    m = re.match(r"^(bat_xanh|bat_do|bat_vang|tat_do|tat_xanh|tat_vang|unknown):\s*([0-9]+(?:\.[0-9]+)?)$", line)
    if m:
        label = m.group(1)
        value = float(m.group(2))
        root.after(
            0,
            lambda l=label, v=value:
            score_vars[l].set(f"{l}: {v:.2f}%")
        )
        return

    if line.startswith("PREDICTION "):
        parts = line.split()
        if len(parts) >= 3:
            label = parts[1]
            try:
                value = float(parts[2])
            except ValueError:
                return
            root.after(
                0,
                lambda l=label, v=value:
                prediction_var.set(f"Dự đoán: {l} ({v:.2f}%)")
            )
        return

    if line.startswith("LED_ACTION "):
        action = line[len("LED_ACTION "):].strip()
        root.after(
            0,
            lambda a=action:
            led_action_var.set(f"LED: {a}")
        )


def play_last_wav():
    if not last_wav_path:
        messagebox.showinfo("Chưa có file", "Hãy thu một file WAV trước.")
        return

    if not os.path.exists(last_wav_path):
        messagebox.showerror("Không tìm thấy WAV", last_wav_path)
        return

    try:
        winsound.PlaySound(
            last_wav_path,
            winsound.SND_FILENAME | winsound.SND_ASYNC
        )
        add_log(f"▶ Đang phát: {last_wav_path}")
    except Exception as e:
        messagebox.showerror("Lỗi phát WAV", str(e))


def stop_wav():
    try:
        winsound.PlaySound(None, 0)
    except Exception:
        pass


# ============================================================
# LƯU WAV
# ============================================================

def save_wav(class_name, number, header, audio):
    folder = os.path.join(DATASET_FOLDER, class_name)
    os.makedirs(folder, exist_ok=True)

    filename = f"{class_name}_{number:03d}.wav"
    filepath = os.path.join(folder, filename)

    with open(filepath, "wb") as f:
        f.write(header)
        f.write(audio)

    return filepath


# ============================================================
# MỞ SERIAL
# ============================================================

def connect_serial():
    global ser

    if ser is not None and ser.is_open:
        return True

    port = combo_port.get()

    if not port:
        messagebox.showwarning("Chưa chọn COM", "Hãy chọn COM port của ESP32-S3.")
        return False

    try:
        ser = serial.Serial(port, BAUDRATE, timeout=0.2)
        time.sleep(2)
        ser.reset_input_buffer()
        add_log(f"Đã kết nối {port}.")
        return True
    except Exception as e:
        messagebox.showerror("Không mở được COM", str(e))
        return False


# ============================================================
# GHI MỘT FILE 1 GIÂY THEO PROTOCOL MỚI
# ============================================================

def record_one_file_worker():
    global busy

    class_name = combo_class.get()

    try:
        current_number = get_next_number(class_name)
        set_file_count(f"File tiếp theo: {current_number:03d}")
        add_log(f"=== Bắt đầu thu {RECORD_SECONDS} giây: {class_name} #{current_number:03d} ===")
        set_status(f"Đang ghi file {current_number:03d}...")

        ser.reset_input_buffer()
        time.sleep(0.2)
        ser.write(b"START\n")
        ser.flush()

        line = wait_for_message(["RECORDING_STARTED"], timeout_seconds=10.0)
        if not line.startswith("RECORDING_STARTED"):
            raise RuntimeError(f"ESP32 không báo RECORDING_STARTED: {line}")

        line = wait_for_message(["WAV_START"], timeout_seconds=15.0)
        if not line.startswith("WAV_START"):
            raise RuntimeError(f"ESP32 không báo WAV_START: {line}")

        parts = line.split()
        if len(parts) < 3:
            raise RuntimeError(f"Dữ liệu WAV_START không hợp lệ: {line}")

        try:
            data_size = int(parts[2])
        except ValueError:
            raise RuntimeError(f"Kích thước WAV_START không hợp lệ: {line}")

        if data_size != AUDIO_BYTES:
            raise RuntimeError(f"Kích thước WAV không đúng. Mong đợi {AUDIO_BYTES}, nhận {data_size}")

        header = read_exact(WAV_HEADER_SIZE)
        if not validate_wav_header(header):
            raise RuntimeError("WAV header không hợp lệ.")

        audio = read_exact(data_size)
        if len(audio) != data_size:
            raise RuntimeError(f"Nhận audio không đủ: {len(audio)} / {data_size}")

        while True:
            line = wait_for_message(["WAV_END", "READY_FOR_NEXT_START"], timeout_seconds=15.0)
            if line.startswith("WAV_END"):
                break
            if line == "READY_FOR_NEXT_START":
                break

        filepath = save_wav(class_name, current_number, header, audio)

        global last_wav_path
        last_wav_path = os.path.abspath(filepath)

        # Đợi và hiển thị đúng 7 kết quả từ Edge Impulse.
        reset_ai_display()
        root.after(0, lambda: prediction_var.set("Dự đoán: đang xử lý..."))

        ai_deadline = time.monotonic() + 15.0
        while time.monotonic() < ai_deadline:
            if ser.in_waiting:
                raw = ser.readline()
                if raw:
                    line = raw.decode("utf-8", errors="ignore").strip()
                    if line:
                        add_log("[AI] " + line)
                        parse_ai_line(line)
                        if line == "AI_END":
                            break
            else:
                time.sleep(0.01)

        add_log(f"Đã lưu file: {filepath}")
        set_file_count(
            f"Đã lưu: {current_number:03d} | Có thể nghe lại"
        )
        set_status(
            f"Đã thu {RECORD_SECONDS} giây + nhận dạng AI."
        )

    except Exception as e:
        set_status("Lỗi ghi âm.")
        add_log(f"LỖI: {e}")
        root.after(0, lambda err=e: messagebox.showerror("Lỗi", str(err)))

    finally:
        busy = False
        set_buttons_enabled(True)


def start_recording():
    global busy, worker_thread

    if busy:
        return

    class_name = combo_class.get()
    if not class_name:
        messagebox.showwarning("Chưa chọn class", "Hãy chọn class cần thu.")
        return

    if not connect_serial():
        return

    busy = True
    set_buttons_enabled(False)
    set_status("Đang gửi lệnh START đến ESP32...")
    add_log(f"=== Bắt đầu ghi {RECORD_SECONDS} giây ===")

    worker_thread = threading.Thread(target=record_one_file_worker, daemon=True)
    worker_thread.start()


# ============================================================
# MỞ THƯ MỤC DATASET
# ============================================================

def open_dataset():
    path = os.path.abspath(DATASET_FOLDER)
    os.makedirs(path, exist_ok=True)

    try:
        os.startfile(path)
    except AttributeError:
        import subprocess
        import sys

        if sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])


# ============================================================
# ĐÓNG CHƯƠNG TRÌNH
# ============================================================

def close_program():
    global busy
    busy = False
    stop_wav()

    try:
        if ser is not None and ser.is_open:
            ser.close()
    except Exception:
        pass

    root.destroy()


# ============================================================
# GIAO DIỆN
# ============================================================

root = tk.Tk()
root.title("ESP32-S3 Voice Dataset Recorder")
root.geometry("900x760")
root.resizable(False, False)

# ---------------- TITLE ----------------

title = ttk.Label(root, text="ESP32-S3 + INMP441", font=("Arial", 20, "bold"))
title.pack(pady=(20, 5))

subtitle = ttk.Label(root, text=f"Voice Dataset Recorder - Thu {RECORD_SECONDS} giây / lần", font=("Arial", 12))
subtitle.pack(pady=(0, 20))

# ---------------- FRAME CẤU HÌNH ----------------

config_frame = ttk.LabelFrame(root, text="Cấu hình", padding=15)
config_frame.pack(padx=20, fill="x")

ttk.Label(config_frame, text="ESP32 COM:").grid(row=0, column=0, sticky="w", padx=5, pady=5)

combo_port = ttk.Combobox(config_frame, width=20, state="readonly")
combo_port.grid(row=0, column=1, padx=5, pady=5)

btn_refresh = ttk.Button(config_frame, text="Refresh", command=refresh_ports)
btn_refresh.grid(row=0, column=2, padx=5, pady=5)

ttk.Label(config_frame, text="Class:").grid(row=1, column=0, sticky="w", padx=5, pady=5)

combo_class = ttk.Combobox(config_frame, values=CLASSES, width=20, state="readonly")
combo_class.grid(row=1, column=1, padx=5, pady=5)
combo_class.current(0)

# ---------------- FORMAT ----------------

format_label = ttk.Label(
    root,
    text=f"WAV: PCM 16-bit | 16 kHz | Mono | {RECORD_SECONDS} giây / file | Chỉ ghi khi nhấn BẮT ĐẦU",
    font=("Arial", 11)
)
format_label.pack(pady=15)

# ---------------- FILE COUNT / STATUS ----------------

file_count_var = tk.StringVar()
file_count_var.set("Chưa bắt đầu")
file_count_label = ttk.Label(root, textvariable=file_count_var, font=("Arial", 12))
file_count_label.pack(pady=5)

status_var = tk.StringVar()
status_var.set("Sẵn sàng")
status_label = ttk.Label(root, textvariable=status_var, font=("Arial", 13))
status_label.pack(pady=5)

# ---------------- EDGE IMPULSE RESULT ----------------

result_frame = ttk.LabelFrame(
    root,
    text="Edge Impulse - 7 nhãn",
    padding=10
)
result_frame.pack(padx=20, pady=(5, 5), fill="x")

score_vars = {}

for i, label in enumerate(AI_LABELS):
    score_vars[label] = tk.StringVar(
        value=f"{label}: 0.00%"
    )

    ttk.Label(
        result_frame,
        textvariable=score_vars[label],
        font=("Consolas", 10)
    ).grid(
        row=i // 4,
        column=i % 4,
        padx=10,
        pady=3,
        sticky="w"
    )

prediction_var = tk.StringVar(value="Dự đoán: ---")
ttk.Label(
    result_frame,
    textvariable=prediction_var,
    font=("Arial", 12, "bold")
).grid(
    row=2,
    column=0,
    columnspan=2,
    padx=10,
    pady=5,
    sticky="w"
)

led_action_var = tk.StringVar(value="LED: ---")
ttk.Label(
    result_frame,
    textvariable=led_action_var,
    font=("Arial", 12, "bold")
).grid(
    row=2,
    column=2,
    columnspan=2,
    padx=10,
    pady=5,
    sticky="w"
)


# ---------------- BUTTON ----------------

mode_frame = ttk.LabelFrame(
    root,
    text="Ghi âm / nghe lại",
    padding=10
)
mode_frame.pack(padx=20, pady=(5, 5), fill="x")

btn_start = ttk.Button(mode_frame, text=f"🎙 BẮT ĐẦU GHI {RECORD_SECONDS}S", command=start_recording)
btn_start.grid(row=0, column=0, padx=10)

btn_open = ttk.Button(mode_frame, text="📁 MỞ DATASET", command=open_dataset)
btn_open.grid(row=0, column=1, padx=10)

btn_play = ttk.Button(
    mode_frame,
    text="▶ NGHE FILE VỪA THU",
    command=play_last_wav
)
btn_play.grid(row=0, column=2, padx=10)

btn_stop = ttk.Button(
    mode_frame,
    text="■ DỪNG PHÁT",
    command=stop_wav
)
btn_stop.grid(row=0, column=3, padx=10)

# ---------------- LOG ----------------

log_frame = ttk.LabelFrame(root, text="Log", padding=5)
log_frame.pack(padx=20, pady=10, fill="both", expand=True)

text_log = tk.Text(log_frame, height=12, state="disabled", font=("Consolas", 10))
text_log.pack(fill="both", expand=True)

# ---------------- KHỞI TẠO ----------------

refresh_ports()
root.protocol("WM_DELETE_WINDOW", close_program)
root.mainloop()