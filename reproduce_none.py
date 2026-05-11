from machine import Pin, I2C

# Probeer eerst I2C bus 1 (jouw huidige setup)
i2c = I2C(1, scl=Pin(27), sda=Pin(26), freq=400000)
print("Scannen op I2C bus 1...")
devices = i2c.scan()

if devices:
    for d in devices:
        print("I2C apparaat gevonden op adres: " + hex(d))
else:
    print("Geen I2C apparaten gevonden op bus 1.")

    # Probeer I2C bus 0 als bus 1 faalt
    print("\nScannen op I2C bus 0...")
    i2c = I2C(0, scl=Pin(28), sda=Pin(27), freq=400000)
    devices = i2c.scan()
    if devices:
        for d in devices:
            print("I2C apparaat gevonden op adres: " + hex(d))
    else:
        print("Ook geen apparaten op bus 0. Controleer bedrading!")