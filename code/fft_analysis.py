# ============================================================
# PHÂN TÍCH TÍN HIỆU ÂM THANH: MIỀN THỜI GIAN + MIỀN TẦN SỐ (FFT)
# Dùng cho báo cáo đồ án - hệ thống điều khiển LED bằng giọng nói
#
# Cách dùng:
#   python fft_analysis.py duong_dan_file.wav
#
# Ví dụ:
#   python fft_analysis.py dataset/bat_xanh/bat_xanh_001.wav
#
# Yêu cầu: pip install numpy scipy matplotlib
# ============================================================

import os
import sys
import wave
from pathlib import Path

try:
    import numpy as np
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from scipy import signal as scipy_signal
except ModuleNotFoundError as exc:
    print(
        "Lỗi: thiếu thư viện bắt buộc. Hãy chạy: python -m pip install numpy scipy matplotlib",
        file=sys.stderr,
    )
    raise SystemExit(1) from exc


def load_wav_mono16(path):
    """Đọc file WAV PCM 16-bit mono, trả về (sample_rate, mảng int16, mảng float trong [-1, 1])."""
    wav_path = Path(path)
    if not wav_path.exists() or not wav_path.is_file():
        raise FileNotFoundError(f"Không tìm thấy file WAV: {path}")

    with wave.open(str(wav_path), "rb") as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        sample_rate = wf.getframerate()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)

    if n_frames == 0:
        raise ValueError(f"File WAV rỗng: {path}")

    if sampwidth != 2:
        raise ValueError(f"File không phải PCM 16-bit (sampwidth={sampwidth} bytes)")

    data = np.frombuffer(raw, dtype=np.int16)

    if n_channels > 1:
        data = data.reshape(-1, n_channels)[:, 0]  # chỉ lấy kênh đầu nếu stereo

    # Chuẩn hoá về [-1, 1] CHỈ để vẽ đồ thị (không dùng cho Edge Impulse,
    # vì Edge Impulse cần giá trị PCM int16 gốc, không chuẩn hoá).
    data_float = data.astype(np.float64) / 32768.0

    return sample_rate, data, data_float


def analyze_and_plot(wav_path, out_png="phan_tich_tin_hieu.png"):
    sample_rate, data_int16, data_float = load_wav_mono16(wav_path)
    n_samples = len(data_int16)

    if n_samples < 2:
        raise ValueError(
            f"File WAV quá ngắn để phân tích FFT: {n_samples} mẫu. Cần ít nhất 2 mẫu."
        )

    duration = n_samples / sample_rate

    print(f"File: {wav_path}")
    print(f"Tần số lấy mẫu (sample rate): {sample_rate} Hz")
    print(f"Số mẫu (samples): {n_samples}")
    print(f"Thời lượng: {duration:.3f} giây")
    print(f"Biên độ PCM int16: min={data_int16.min()}, max={data_int16.max()}")

    # ---------------- MIỀN THỜI GIAN ----------------
    t = np.arange(n_samples) / sample_rate

    # ---------------- MIỀN TẦN SỐ (FFT) ----------------
    # Cửa sổ Hamming để giảm rò rỉ phổ (spectral leakage)
    window = np.hamming(n_samples)
    windowed = data_float * window

    fft_result = np.fft.rfft(windowed)
    fft_freqs = np.fft.rfftfreq(n_samples, d=1.0 / sample_rate)
    fft_magnitude_db = 20 * np.log10(np.abs(fft_result) + 1e-12)

    # ---------------- SPECTROGRAM (STFT theo thời gian) ----------------
    nperseg = min(512, n_samples)
    noverlap = min(384, max(0, nperseg // 2))
    f_spec, t_spec, Sxx = scipy_signal.spectrogram(
        data_float,
        fs=sample_rate,
        window="hann",
        nperseg=nperseg,
        noverlap=noverlap,
    )
    Sxx_db = 10 * np.log10(Sxx + 1e-12)

    # ---------------- VẼ ĐỒ THỊ ----------------
    fig, axes = plt.subplots(3, 1, figsize=(10, 11))

    # 1) Miền thời gian
    axes[0].plot(t, data_float, linewidth=0.6, color="tab:blue")
    axes[0].set_title("Tín hiệu miền thời gian (Time domain)")
    axes[0].set_xlabel("Thời gian (s)")
    axes[0].set_ylabel("Biên độ (chuẩn hoá)")
    axes[0].grid(True, alpha=0.3)

    # 2) Miền tần số (FFT)
    axes[1].plot(fft_freqs, fft_magnitude_db, linewidth=0.7, color="tab:orange")
    axes[1].set_title("Phổ tần số (FFT Magnitude Spectrum)")
    axes[1].set_xlabel("Tần số (Hz)")
    axes[1].set_ylabel("Biên độ (dB)")
    axes[1].set_xlim(0, sample_rate / 2)  # tới tần số Nyquist
    axes[1].grid(True, alpha=0.3)

    # 3) Spectrogram
    pcm = axes[2].pcolormesh(t_spec, f_spec, Sxx_db, shading="gouraud", cmap="viridis")
    axes[2].set_title("Spectrogram (biến thiên phổ tần số theo thời gian)")
    axes[2].set_xlabel("Thời gian (s)")
    axes[2].set_ylabel("Tần số (Hz)")
    axes[2].set_ylim(0, sample_rate / 2)
    fig.colorbar(pcm, ax=axes[2], label="Công suất (dB)")

    fig.tight_layout()
    out_path = Path(out_png)
    if out_path.parent and not out_path.parent.exists():
        out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(out_path), dpi=150)
    print(f"\nĐã lưu hình phân tích vào: {out_path}")

    return {
        "sample_rate": sample_rate,
        "n_samples": n_samples,
        "duration": duration,
        "fft_freqs": fft_freqs,
        "fft_magnitude_db": fft_magnitude_db,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Cách dùng: python fft_analysis.py duong_dan_file.wav")
        sys.exit(1)

    try:
        analyze_and_plot(sys.argv[1])
    except (FileNotFoundError, ValueError) as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        sys.exit(1)
