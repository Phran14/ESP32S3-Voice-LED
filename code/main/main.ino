#include <ESP32S3_VOICE_LED_inferencing.h>
//#include <ESP32S3_VOICE_LED_inferencing.h>

#include <Arduino.h>
#include <ESP_I2S.h>

// Nếu chỉ thu WAV thì KHÔNG cần dòng này.
// Nếu sau này chạy AI thì bỏ comment và giữ đúng 1 dòng.
// #include <ESP32S3_VOICE_LED_inferencing.h>

// ======================================================
// ESP32-S3 N16R8 + INMP441
//
// INMP441:
// VDD  -> 3V3
// GND  -> GND
// SCK  -> GPIO 4
// WS   -> GPIO 5
// SD   -> GPIO 6
// L/R  -> GND
// ======================================================

#define I2S_BCLK  4
#define I2S_WS    5
#define I2S_DIN   6

// ======================================================
// LED + EXACT EDGE IMPULSE LABELS
// ======================================================
#define LED_DO_PIN    21
#define LED_VANG_PIN  47
#define LED_XANH_PIN  48

// KHÔNG có noise. Chỉ đúng 7 nhãn của model.
const char *LABEL_BAT_XANH  = "bat_xanh";
const char *LABEL_BAT_DO    = "bat_do";
const char *LABEL_BAT_VANG  = "bat_vang";
const char *LABEL_TAT_DO    = "tat_do";
const char *LABEL_TAT_XANH  = "tat_xanh";
const char *LABEL_TAT_VANG  = "tat_vang";
const char *LABEL_UNKNOWN   = "unknown";


I2SClass I2S;

// ======================================================
// AUDIO CONFIG
// ======================================================

#define SAMPLE_RATE       16000
#define RECORD_SECONDS    2

// 16000 × 2 = 32000 samples
#define NUM_SAMPLES       (SAMPLE_RATE * RECORD_SECONDS)

#define I2S_BUFFER_SIZE   256

// INMP441 32-bit -> PCM 16-bit
#define MIC_SHIFT         14

int32_t i2sBuffer[I2S_BUFFER_SIZE];

int16_t audioBuffer[NUM_SAMPLES];

// ======================================================
// FILE NUMBER
// ======================================================

uint32_t fileNumber = 1;


// ======================================================
// TẠO WAV HEADER
// ======================================================

void createWavHeader(uint8_t *header, uint32_t dataSize)
{
    uint32_t fileSize = 36 + dataSize;

    uint16_t audioFormat = 1;
    uint16_t channels = 1;
    uint32_t sampleRate = SAMPLE_RATE;
    uint16_t bitsPerSample = 16;

    uint32_t byteRate =
        sampleRate *
        channels *
        bitsPerSample / 8;

    uint16_t blockAlign =
        channels *
        bitsPerSample / 8;

    // --------------------------------------------------
    // RIFF
    // --------------------------------------------------

    header[0] = 'R';
    header[1] = 'I';
    header[2] = 'F';
    header[3] = 'F';

    header[4] = fileSize & 0xFF;
    header[5] = (fileSize >> 8) & 0xFF;
    header[6] = (fileSize >> 16) & 0xFF;
    header[7] = (fileSize >> 24) & 0xFF;

    header[8]  = 'W';
    header[9]  = 'A';
    header[10] = 'V';
    header[11] = 'E';

    // --------------------------------------------------
    // fmt
    // --------------------------------------------------

    header[12] = 'f';
    header[13] = 'm';
    header[14] = 't';
    header[15] = ' ';

    header[16] = 16;
    header[17] = 0;
    header[18] = 0;
    header[19] = 0;

    header[20] = audioFormat & 0xFF;
    header[21] = (audioFormat >> 8) & 0xFF;

    header[22] = channels & 0xFF;
    header[23] = (channels >> 8) & 0xFF;

    header[24] = sampleRate & 0xFF;
    header[25] = (sampleRate >> 8) & 0xFF;
    header[26] = (sampleRate >> 16) & 0xFF;
    header[27] = (sampleRate >> 24) & 0xFF;

    header[28] = byteRate & 0xFF;
    header[29] = (byteRate >> 8) & 0xFF;
    header[30] = (byteRate >> 16) & 0xFF;
    header[31] = (byteRate >> 24) & 0xFF;

    header[32] = blockAlign & 0xFF;
    header[33] = (blockAlign >> 8) & 0xFF;

    header[34] = bitsPerSample & 0xFF;
    header[35] = (bitsPerSample >> 8) & 0xFF;

    // --------------------------------------------------
    // data
    // --------------------------------------------------

    header[36] = 'd';
    header[37] = 'a';
    header[38] = 't';
    header[39] = 'a';

    header[40] = dataSize & 0xFF;
    header[41] = (dataSize >> 8) & 0xFF;
    header[42] = (dataSize >> 16) & 0xFF;
    header[43] = (dataSize >> 24) & 0xFF;
}


// ======================================================
// THU ĐÚNG 2 GIÂY
// ======================================================

bool recordTwoSeconds()
{
    memset(
        audioBuffer,
        0,
        sizeof(audioBuffer)
    );

    uint32_t samplesReceived = 0;

    Serial.println();
    Serial.println(
        "================================"
    );
    Serial.println(
        "BAT DAU THU AM 2 GIAY"
    );
    Serial.println(
        "================================"
    );

    while (
        samplesReceived < NUM_SAMPLES
    )
    {
        size_t bytesRead =
            I2S.readBytes(
                (char *)i2sBuffer,
                sizeof(i2sBuffer)
            );

        if (bytesRead == 0)
        {
            continue;
        }

        uint32_t samplesRead =
            bytesRead /
            sizeof(int32_t);

        for (
            uint32_t i = 0;
            i < samplesRead &&
            samplesReceived < NUM_SAMPLES;
            i++
        )
        {
            int32_t sample =
                i2sBuffer[i];

            int32_t pcm =
                sample >> MIC_SHIFT;

            if (pcm > 32767)
                pcm = 32767;

            if (pcm < -32768)
                pcm = -32768;

            audioBuffer[
                samplesReceived
            ] = (int16_t)pcm;

            samplesReceived++;
        }
    }

    Serial.print(
        "Da thu: "
    );

    Serial.print(
        samplesReceived
    );

    Serial.println(
        " samples"
    );

    Serial.println(
        "THU AM XONG - 2 GIAY"
    );

    return (
        samplesReceived ==
        NUM_SAMPLES
    );
}


// ======================================================
// GỬI FILE WAV
// ======================================================

void sendWavFile(
    uint32_t number
)
{
    uint32_t dataSize =
        NUM_SAMPLES *
        sizeof(int16_t);

    uint8_t wavHeader[44];

    createWavHeader(
        wavHeader,
        dataSize
    );

    // --------------------------------------------------
    // Thông tin file
    // --------------------------------------------------

    Serial.print(
        "WAV_START "
    );

    Serial.print(
        number
    );

    Serial.print(
        " "
    );

    Serial.println(
        dataSize
    );

    Serial.flush();

    delay(10);

    // --------------------------------------------------
    // WAV HEADER
    // --------------------------------------------------

    Serial.write(
        wavHeader,
        44
    );

    // --------------------------------------------------
    // AUDIO DATA
    // --------------------------------------------------

    const uint8_t *audioData =
        (const uint8_t *)audioBuffer;

    uint32_t totalBytes =
        dataSize;

    uint32_t sent = 0;

    while (
        sent < totalBytes
    )
    {
        uint32_t chunk =
            min(
                (uint32_t)1024,
                totalBytes - sent
            );

        Serial.write(
            audioData + sent,
            chunk
        );

        sent += chunk;
    }

    Serial.flush();

    // --------------------------------------------------
    // KẾT THÚC
    // --------------------------------------------------

    Serial.println();

    Serial.print(
        "WAV_END "
    );

    Serial.println(
        number
    );

    Serial.flush();
}



// ======================================================
// EDGE IMPULSE: NHẬN DẠNG 7 NHÃN
// ======================================================

static int get_signal_data(size_t offset, size_t length, float *out_ptr)
{
    if (offset + length > NUM_SAMPLES) {
        return -1;
    }

    for (size_t i = 0; i < length; i++) {
        // QUAN TRONG: Edge Impulse dung gia tri PCM int16 GOC (-32768..32767),
        // KHONG chuan hoa ve -1..1. Chia cho 32768 se lam bien do tin hieu
        // nho hon ~32768 lan so voi luc train tren Studio, khien model luon
        // nhan dien la "unknown".
        out_ptr[i] = (float)audioBuffer[offset + i];
    }

    return 0;
}

void controlLED(const char *label, float confidence)
{
    // Chỉ nhận lệnh khi confidence >= 60%.
    // unknown hoặc confidence thấp => không thay đổi LED.
    if (confidence < 0.60f) {
        Serial.println("LED_ACTION NONE_LOW_CONFIDENCE");
        return;
    }

    if (strcmp(label, LABEL_BAT_XANH) == 0) {
        digitalWrite(LED_XANH_PIN, HIGH);
    }
    else if (strcmp(label, LABEL_BAT_DO) == 0) {
        digitalWrite(LED_DO_PIN, HIGH);
    }
    else if (strcmp(label, LABEL_BAT_VANG) == 0) {
        digitalWrite(LED_VANG_PIN, HIGH);
    }
    else if (strcmp(label, LABEL_TAT_DO) == 0) {
        digitalWrite(LED_DO_PIN, LOW);
    }
    else if (strcmp(label, LABEL_TAT_XANH) == 0) {
        digitalWrite(LED_XANH_PIN, LOW);
    }
    else if (strcmp(label, LABEL_TAT_VANG) == 0) {
        digitalWrite(LED_VANG_PIN, LOW);
    }
    else {
        // unknown: không làm gì.
        Serial.println("LED_ACTION NONE_UNKNOWN");
        return;
    }

    Serial.print("LED_ACTION ");
    Serial.println(label);
}

void runVoiceAI()
{
    signal_t signal;
    signal.total_length = NUM_SAMPLES;
    signal.get_data = get_signal_data;

    ei_impulse_result_t result = {};
    EI_IMPULSE_ERROR err = run_classifier(&signal, &result, false);

    if (err != EI_IMPULSE_OK) {
        Serial.print("AI_ERROR ");
        Serial.println((int)err);
        return;
    }

    float bat_xanh = 0.0f;
    float bat_do   = 0.0f;
    float bat_vang = 0.0f;
    float tat_do   = 0.0f;
    float tat_xanh = 0.0f;
    float tat_vang = 0.0f;
    float unknown  = 0.0f;

    // Lấy điểm theo TÊN NHÃN, tuyệt đối không dựa vào thứ tự index.
    for (size_t i = 0; i < EI_CLASSIFIER_LABEL_COUNT; i++) {
        const char *label = result.classification[i].label;
        float score = result.classification[i].value;

        if (strcmp(label, LABEL_BAT_XANH) == 0) {
            bat_xanh = score;
        }
        else if (strcmp(label, LABEL_BAT_DO) == 0) {
            bat_do = score;
        }
        else if (strcmp(label, LABEL_BAT_VANG) == 0) {
            bat_vang = score;
        }
        else if (strcmp(label, LABEL_TAT_DO) == 0) {
            tat_do = score;
        }
        else if (strcmp(label, LABEL_TAT_XANH) == 0) {
            tat_xanh = score;
        }
        else if (strcmp(label, LABEL_TAT_VANG) == 0) {
            tat_vang = score;
        }
        else if (strcmp(label, LABEL_UNKNOWN) == 0) {
            unknown = score;
        }
        // Nếu model có nhãn khác thì bỏ qua.
    }

    const char *bestLabel = LABEL_UNKNOWN;
    float bestScore = unknown;

    if (bat_xanh > bestScore) {
        bestScore = bat_xanh;
        bestLabel = LABEL_BAT_XANH;
    }
    if (bat_do > bestScore) {
        bestScore = bat_do;
        bestLabel = LABEL_BAT_DO;
    }
    if (bat_vang > bestScore) {
        bestScore = bat_vang;
        bestLabel = LABEL_BAT_VANG;
    }
    if (tat_do > bestScore) {
        bestScore = tat_do;
        bestLabel = LABEL_TAT_DO;
    }
    if (tat_xanh > bestScore) {
        bestScore = tat_xanh;
        bestLabel = LABEL_TAT_XANH;
    }
    if (tat_vang > bestScore) {
        bestScore = tat_vang;
        bestLabel = LABEL_TAT_VANG;
    }

    // Protocol cho app Python:
    // AI_START
    // đúng 7 dòng "label: percent"
    // PREDICTION label percent
    // LED_ACTION ...
    // AI_END
    Serial.println("AI_START");

    Serial.print("bat_xanh: ");
    Serial.println(bat_xanh * 100.0f, 2);

    Serial.print("bat_do: ");
    Serial.println(bat_do * 100.0f, 2);

    Serial.print("bat_vang: ");
    Serial.println(bat_vang * 100.0f, 2);

    Serial.print("tat_do: ");
    Serial.println(tat_do * 100.0f, 2);

    Serial.print("tat_xanh: ");
    Serial.println(tat_xanh * 100.0f, 2);

    Serial.print("tat_vang: ");
    Serial.println(tat_vang * 100.0f, 2);

    Serial.print("unknown: ");
    Serial.println(unknown * 100.0f, 2);

    Serial.print("PREDICTION ");
    Serial.print(bestLabel);
    Serial.print(" ");
    Serial.println(bestScore * 100.0f, 2);

    controlLED(bestLabel, bestScore);

    Serial.println("AI_END");
}

// ======================================================
// XỬ LÝ LỆNH
// ======================================================

void checkCommand()
{
    if (!Serial.available())
        return;

    String command =
        Serial.readStringUntil(
            '\n'
        );

    command.trim();

    command.toUpperCase();

    // ==================================================
    // TEST: chi ghi am + chay AI, KHONG gui WAV nhi phan.
    // Dung lenh nay khi test bang Serial Monitor thuong,
    // de tranh ky tu lon xon do du lieu am thanh tho.
    // ==================================================

    if (command == "TEST")
    {
        Serial.println(
            "RECORDING_STARTED"
        );

        Serial.flush();

        bool success =
            recordTwoSeconds();

        if (!success)
        {
            Serial.println(
                "ERROR: RECORD FAILED"
            );

            Serial.flush();

            return;
        }

        // KHONG goi sendWavFile() o day.
        runVoiceAI();

        Serial.println(
            "READY_FOR_NEXT_START"
        );

        Serial.flush();

        return;
    }

    // ==================================================
    // START
    // ==================================================

    if (
        command == "START" ||
        command == "ONE"
    )
    {
        Serial.println(
            "RECORDING_STARTED"
        );

        Serial.flush();

        // THU ĐÚNG 2 GIÂY
        bool success =
            recordTwoSeconds();

        if (!success)
        {
            Serial.println(
                "ERROR: RECORD FAILED"
            );

            Serial.flush();

            return;
        }

        // GỬI WAV cho app để lưu file.
        sendWavFile(
            fileNumber
        );

        // Chạy Edge Impulse trên chính audio vừa thu.
        runVoiceAI();

        fileNumber++;

        Serial.println(
            "READY_FOR_NEXT_START"
        );

        Serial.flush();
    }

    // ==================================================
    // RESET SỐ FILE
    // ==================================================

    else if (
        command == "RESET"
    )
    {
        fileNumber = 1;

        Serial.println(
            "FILE_NUMBER_RESET"
        );

        Serial.flush();
    }

    // ==================================================
    // STOP BỊ BỎ QUA
    // ==================================================

    else if (
        command == "STOP"
    )
    {
        // Không làm gì
    }
}


// ======================================================
// SETUP
// ======================================================

void setup()
{
    Serial.begin(
        921600
    );

    delay(2000);

    Serial.println();
    Serial.println(
        "========================================"
    );
    Serial.println(
        "ESP32-S3 N16R8"
    );
    Serial.println(
        "INMP441 WAV RECORDER"
    );
    Serial.println(
        "========================================"
    );

    Serial.print(
        "Sample rate: "
    );

    Serial.print(
        SAMPLE_RATE
    );

    Serial.println(
        " Hz"
    );

    Serial.print(
        "Record time: "
    );

    Serial.print(
        RECORD_SECONDS
    );

    Serial.println(
        " seconds"
    );

    Serial.print(
        "Total samples: "
    );

    Serial.println(
        NUM_SAMPLES
    );

    Serial.println();

    // ==================================================
    // LED PIN
    // ==================================================
    pinMode(LED_DO_PIN, OUTPUT);
    pinMode(LED_VANG_PIN, OUTPUT);
    pinMode(LED_XANH_PIN, OUTPUT);

    digitalWrite(LED_DO_PIN, LOW);
    digitalWrite(LED_VANG_PIN, LOW);
    digitalWrite(LED_XANH_PIN, LOW);

    // ==================================================
    // I2S PIN
    // ==================================================

    I2S.setPins(
        I2S_BCLK,
        I2S_WS,
        -1,
        I2S_DIN,
        -1
    );

    // ==================================================
    // I2S
    // ==================================================

    if (
        !I2S.begin(
            I2S_MODE_STD,
            SAMPLE_RATE,
            I2S_DATA_BIT_WIDTH_32BIT,
            I2S_SLOT_MODE_MONO
        )
    )
    {
        Serial.println(
            "ERROR: I2S INIT FAILED"
        );

        while (true)
        {
            delay(1000);
        }
    }

    Serial.println(
        "I2S INITIALIZED"
    );

    Serial.println();
    Serial.println(
        "========================================"
    );
    Serial.println(
        "SAN SANG"
    );
    Serial.println(
        "Gui START de thu 2 giay."
    );
    Serial.println(
        "Gui START lan nua de thu file tiep."
    );
    Serial.println(
        "========================================"
    );
}


// ======================================================
// LOOP
// ======================================================

void loop()
{
    checkCommand();

    delay(2);
}
