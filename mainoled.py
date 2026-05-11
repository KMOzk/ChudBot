from machine import Pin, I2C
import ssd1306
import time
import network
import urequests

# --- VUL DIT IN ---
def load_env():
    env = {}
    try:
        with open('.env', 'r') as f:
            for line in f:
                if '=' in line:
                    key, value = line.strip().split('=', 1)
                    env[key] = value
    except Exception:
        pass
    return env

env = load_env()
WIFI_SSID = env.get('WIFI_SSID')
WIFI_PASS = env.get('WIFI_PASS')
FLASK_API_URL = env.get('FLASK_API_URL', 'http://192.168.x.x:5000/api/oled')
try:
    i2c = I2C(1, scl=Pin(28), sda=Pin(27), freq=400000)
    display = ssd1306.SSD1306_I2C(128, 64, i2c)
except Exception as e:
    print("OLED Fout:", e)
    # Als de OLED niet gevonden wordt, stopt de code hier veilig.


def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        display.fill(0)
        display.text("Verbinden met", 0, 0)
        display.text("WiFi...", 0, 10)
        display.show()
        wlan.connect(WIFI_SSID, WIFI_PASS)

        while not wlan.isconnected():
            time.sleep(0.5)

    display.fill(0)
    display.text("WiFi Verbonden!", 0, 0)
    display.text(wlan.ifconfig()[0], 0, 20)
    display.show()
    time.sleep(2)


def update_display(text_data):
    display.fill(0)
    lines = text_data.split('\n')

    y = 0
    for line in lines[:6]:
        display.text(line, 0, y)
        y += 10

    display.show()


def run():
    connect_wifi()

    while True:
        try:
            print("Gegevens ophalen van server...")
            response = urequests.get(FLASK_API_URL)
            event_text = response.text
            response.close()

            if not event_text.strip():
                event_text = "Geen afspraken\nvandaag!"

            update_display(event_text)
            print("Scherm geupdate!")

        except Exception as e:
            print("Fout bij ophalen:", e)
            display.fill(0)
            display.text("Kan server", 0, 0)
            display.text("niet bereiken...", 0, 10)
            display.show()

        # Wacht 10 seconden voor deze test (normaal is 5 min beter)
        time.sleep(10)


# Start de loop
run()