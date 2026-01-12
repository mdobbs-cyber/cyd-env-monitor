import network
import ntptime
import time
import machine
import ujson

def connect_wifi():
    # Load config
    try:
        with open('config.json', 'r') as f:
            config = ujson.load(f)
            ssid = config.get('ssid')
            password = config.get('password')
    except Exception as e:
        print("Failed to load config.json:", e)
        return

    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print(f'Connecting to WiFi ({ssid})...')
        wlan.connect(ssid, password)
        for _ in range(20):
            if wlan.isconnected():
                break
            time.sleep(1)
    
    if wlan.isconnected():
        print('Connected! IP:', wlan.ifconfig()[0])
        try:
            print('Syncing time with NTP...')
            ntptime.settime()
            print('Time synced.')
        except Exception as e:
            print('NTP sync failed:', e)
    else:
        print('WiFi connection failed.')

# Call connect_wifi() at the end or in main.py
