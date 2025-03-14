import librosa
import math
import numpy as np
import matplotlib.pyplot as plt


def convert_audio_to_v3_protocol(mp3_file_path: str) -> list:
    """
    讀取MP3文件並將其轉換為V3協議格式的頻率和強度數據
    每100ms生成一組數據


    返回:
    list: 格式為 [[[頻率, 頻率, 頻率, 頻率], [強度, 強度, 強度, 強度]], ...] 的數據
    """
    y, sr = librosa.load(mp3_file_path, sr=None)

    duration_sec = len(y) / sr
    required_groups = math.ceil(duration_sec * 10)
    hop_length = int(sr * 0.025)
    n_fft = 2048
    D = librosa.stft(y, n_fft=n_fft, hop_length=hop_length)
    S_db = librosa.amplitude_to_db(np.abs(D), ref=np.max)
    rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]
    result = []
    total_frames = S_db.shape[1]
    frames_per_group = total_frames / required_groups

    for i in range(required_groups):
        start_frame = int(i * frames_per_group)
        end_frame = int(min((i + 1) * frames_per_group, total_frames))
        if end_frame <= start_frame:
            end_frame = start_frame + 1

        frames_to_sample = []
        if end_frame - start_frame >= 4:
            for j in range(4):
                frames_to_sample.append(start_frame + int(j * (end_frame - start_frame) / 4))
        else:
            while len(frames_to_sample) < 4:
                for frame in range(start_frame, end_frame):
                    frames_to_sample.append(frame)
                    if len(frames_to_sample) >= 4:
                        break

        frames_to_sample = frames_to_sample[:4]

        freq_data = []
        intensity_data = []

        for frame in frames_to_sample:
            if frame < total_frames:
                spectrum = S_db[:, frame]

                dominant_freq_idx = np.argmax(spectrum)
                dominant_freq = librosa.fft_frequencies(sr=sr, n_fft=n_fft)[dominant_freq_idx]

                waveform_freq_ms = 1000 / dominant_freq if dominant_freq > 0 else 1000

                waveform_freq_ms = max(10, min(1000, waveform_freq_ms))

                v3_freq = convert_to_v3_frequency(waveform_freq_ms)

                frame_energy = rms[min(frame, len(rms) - 1)]

                max_rms = np.max(rms)
                min_rms = np.min(rms)
                normalized_energy = (frame_energy - min_rms) / (max_rms - min_rms + 1e-10)
                intensity = int(normalized_energy * 100)
                intensity = max(0, min(100, intensity))

                freq_data.append(v3_freq)
                intensity_data.append(intensity)
            else:
                freq_data.append(0)
                intensity_data.append(0)

        while len(freq_data) < 4:
            freq_data.append(0)
        while len(intensity_data) < 4:
            intensity_data.append(0)

        result.append([freq_data, intensity_data])

    return result


def convert_to_v3_frequency(waveform_freq_ms: int) -> int:
    """
    10ms-1000ms to 10-240
    """
    # 確保10-1000ms
    waveform_freq_ms = max(10, min(1000, waveform_freq_ms))

    if waveform_freq_ms <= 100:
        return int(waveform_freq_ms)
    elif waveform_freq_ms <= 150:
        return int(100 + (waveform_freq_ms - 100) / 5)
    elif waveform_freq_ms <= 1000:
        return int(110 + 130 * (math.log(waveform_freq_ms / 150) / math.log(1000 / 150)))
    return 0


def analyze_and_visualize_audio(mp3_file_path: str) -> dict:
    """
    debug
    """
    y, sr = librosa.load(mp3_file_path, sr=None)
    rms = librosa.feature.rms(y=y)[0]
    zero_crossings = librosa.feature.zero_crossing_rate(y)[0]

    D = librosa.stft(y)
    magnitude = librosa.amplitude_to_db(np.abs(D), ref=np.max)
    plt.figure(figsize=(15, 10))

    plt.subplot(3, 1, 1)
    librosa.display.waveshow(y, sr=sr)
    plt.title("Waveform")

    plt.subplot(3, 1, 2)
    librosa.display.specshow(magnitude, sr=sr, x_axis="time", y_axis="log")
    plt.colorbar(format="%+2.0f dB")
    plt.title("Spectrogram")

    plt.subplot(3, 1, 3)
    times = librosa.times_like(rms, sr=sr)
    plt.plot(times, rms, label="RMS Energy")
    plt.plot(times, zero_crossings, label="Zero Crossing Rate", alpha=0.7)
    plt.legend()
    plt.title("Audio Features")

    plt.tight_layout()
    plt.savefig("audio_analysis.png")
    plt.close()

    return {
        "duration": len(y) / sr,
        "sample_rate": sr,
        "mean_rms": np.mean(rms),
        "max_rms": np.max(rms),
        "mean_zero_crossings": np.mean(zero_crossings),
    }


if __name__ == "__main__":
    mp3_file_path = "CruelMilkman-VOL5.mp3"

    analysis = analyze_and_visualize_audio(mp3_file_path)
    print("轉換結果:")
    for key, value in analysis.items():
        print(f"    {key}: {value}")
    print(f"時間: {analysis['duration']:.2f}秒")

    data = convert_audio_to_v3_protocol(mp3_file_path)
    for i, item in enumerate(data[:5]):
        print(f"    組 {i + 1}: {item}")
