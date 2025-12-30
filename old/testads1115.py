import sys
import board
import busio

i2c = busio.I2C(board.SCL, board.SDA)

print("I2C devices found: ", [hex(i) for i in i2c.scan()])

ads1115_1 = 0x48
ads1115_2 = 0x49

if not ads1115_1 in i2c.scan():
    print("could not find ads1115_1")
    sys.exit

if not ads1115_2 in i2c.scan():
    print("could not find ads1115_2")
    sys.exit

def get_adc_ids():
    i2c.writeto(ads1115_1, bytes([0xd0]), stop=False)
    i2c.writeto(ads1115_2, bytes([0xd0]), stop=False)
    result1 = bytearray(1);
    result2 = bytearray(1);
    i2c.readfrom_into(ads1115_1, result1)
    i2c.readfrom_into(ads1115_2, result2)
    print("ADS1115_1 ID: ", int.from_bytes(result1, "big"))
    print("ADS1115_2 ID: ", int.from_bytes(result2, "big"))

if __name__ == "__main__":
    get_adc_ids()
