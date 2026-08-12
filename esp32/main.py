import network
import urequests
import time
from machine import Pin, SPI
from mfrc522 import MFRC522

# WiFi Configuration
SSID = "YOUR_SSID"
PASSWORD = "YOUR_PASSWORD"
BACKEND_URL = "http://192.168.1.100:5001"  # Change to your PC IP

# GPIO pins
BUZZER_PIN = 26
LED_PIN = 2

# Initialize hardware
spi = SPI(1, baudrate=1000000, polarity=0, phase=0, sck=Pin(18), mosi=Pin(23), miso=Pin(19))
rfid = MFRC522(8, Pin(5), spi)  # cs=GPIO5, spi bus 1
buzzer = Pin(BUZZER_PIN, Pin.OUT)
led = Pin(LED_PIN, Pin.OUT)

def beep_buzzer(times=1, duration_ms=100):
    """Beep buzzer N times"""
    for _ in range(times):
        buzzer.on()
        time.sleep_ms(duration_ms)
        buzzer.off()
        time.sleep_ms(50)

def blink_led(times=1):
    """Blink LED N times"""
    for _ in range(times):
        led.on()
        time.sleep_ms(200)
        led.off()
        time.sleep_ms(200)

def connect_wifi():
    """Connect to WiFi"""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(SSID, PASSWORD)

    print("Connecting to WiFi...")
    for i in range(20):
        if wlan.isconnected():
            print(f"WiFi connected: {wlan.ifconfig()}")
            blink_led(2)
            return True
        time.sleep(1)

    print("WiFi connection failed")
    beep_buzzer(5, 100)
    return False

def uid_to_hex(uid):
    """Convert UID bytes to hex string (e.g., 'A1B2C3D4')"""
    return ''.join(f'{b:02X}' for b in uid[:4])

def post_rfid_to_backend(tag_uid):
    """POST RFID tag to backend"""
    url = f"{BACKEND_URL}/api/puestos/engastado_v3/entrada"
    data = {"tag_uid": tag_uid}

    try:
        response = urequests.post(url, json=data, timeout=5)
        status = response.status_code

        if status == 200:
            result = response.json()
            print(f"✓ Success: {result.get('operario_nombre')}")
            beep_buzzer(2, 100)
            led.on()
            time.sleep(1)
            led.off()
            return True
        else:
            print(f"✗ Error: Status {status}")
            beep_buzzer(1, 150)
            return False
    except Exception as e:
        print(f"Network error: {e}")
        beep_buzzer(5, 100)
        return False

def main():
    """Main loop: read RFID and post to backend"""
    print("ESP32 RFID Reader - Engastado V3")
    print("=" * 50)

    if not connect_wifi():
        print("Reboot to retry WiFi connection")
        while True:
            time.sleep(1)

    print("\nWaiting for RFID card scan...")
    blink_led(1)

    last_scan_time = 0
    DEBOUNCE_MS = 2000  # 2 second debounce between reads

    while True:
        rfid.irq.handler()
        rfid.scan()
        rfid.select_tag(rfid.uid)

        if rfid.uid:
            current_time = time.ticks_ms()
            if current_time - last_scan_time > DEBOUNCE_MS:
                tag_uid = uid_to_hex(rfid.uid)
                print(f"\nCard detected: {tag_uid}")
                post_rfid_to_backend(tag_uid)
                last_scan_time = current_time

        time.sleep(0.1)

if __name__ == "__main__":
    main()
