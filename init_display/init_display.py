#!/usr/bin/python

import os
import sys
import subprocess
import time
import logging
import datetime
import psutil
import struct
import smbus
import gpiod
from PIL import Image, ImageDraw, ImageFont

# Configure logging
logging.basicConfig(level=logging.DEBUG)

# Constants
FONT_SIZE = 12
LEFT_PADDING = 1
SM_BUS = 1
PLD_PIN = 6
ADDRESS = 0x36
SLEEP_TIME_AC = 1
SLEEP_TIME_BAT = 10

# Directories
script_path = os.path.realpath(__file__)
picdir = os.path.join(os.path.dirname(script_path), 'pic')
libdir = os.path.join(os.path.dirname(script_path), 'lib')

if os.path.exists(libdir):
    sys.path.append(libdir)

from waveshare_OLED import OLED_1in3

# Initialize font and display
font = ImageFont.truetype(os.path.join(picdir, 'Font.ttc'), FONT_SIZE)
disp = OLED_1in3.OLED_1in3()
disp.init_display()

def read_word(bus, register):
    """Read a word from the I2C device and return the swapped value."""
    try:
        read = bus.read_word_data(ADDRESS, register)
        return struct.unpack("<H", struct.pack(">H", read))[0]
    except IOError as e:
        logging.error(f"Failed to read from I2C: {e}")
        return 0  # Return 0 or a sensible default in case of failure

def read_voltage(bus):
    """Calculate and return the voltage from the battery."""
    return read_word(bus, 2) * 1.25 / 1000 / 16

def read_capacity(bus):
    """Calculate and return the battery capacity."""
    return round(read_word(bus, 4) / 256, 2)

def get_battery_info(bus, ac_power_state):
    """Return a formatted string with battery capacity and power state."""
    capacity = int(read_capacity(bus))
    power_state = "+" if ac_power_state == 1 else "-"
    return f'{power_state}{capacity}%'

def get_system_info():
    """Fetch current time, CPU temperature, CPU and memory usage."""
    current_time = datetime.datetime.now().strftime('%d-%m-%y %H:%M')
    cpu_temp = subprocess.check_output(['vcgencmd', 'measure_temp']).decode("utf-8").strip().replace('temp=', 't: ').upper()
    cpu_usage = f'CPU: {psutil.cpu_percent(interval=1)}%'
    mem_usage = f'MEM: {psutil.virtual_memory().percent}%'
    return current_time, cpu_temp, cpu_usage, mem_usage

def draw_display(current_time, cpu_temp, cpu_usage, mem_usage, battery_status, network_info):
    """Draw system information on the OLED display."""
    image = Image.new(mode='1', size=(disp.width, disp.height), color="WHITE")
    draw = ImageDraw.Draw(image)

    draw.text((LEFT_PADDING, 0), f"{current_time} | {battery_status}", font=font, fill=0)
    draw.text((LEFT_PADDING, FONT_SIZE), f"{cpu_usage} | {cpu_temp}", font=font, fill=0)
    draw.text((LEFT_PADDING, 2 * FONT_SIZE), mem_usage, font=font, fill=0)
    draw.text((LEFT_PADDING, 3 * FONT_SIZE), network_info, font=font, fill=0)

    return image.rotate(180)

def create_pid_file():
    """Create or remove a PID file for the script."""
    pidfile = "/run/X1200.pid"
    pid = str(os.getpid())

    try:
        if os.path.isfile(pidfile):
            os.remove(pidfile)  # Clean up old PID file
        with open(pidfile, 'w') as f:
            f.write(pid)
    except Exception as e:
        logging.error(f"Error creating PID file: {e}")
        
def get_ip_address():
    ipaddress = os.popen("ifconfig wlan0 \
                     | grep -o 'inet [0-9.]\+' \
                     | awk '{print $2}'").read()
    return ipaddress

def get_wlan_ssid():
    ssid = os.popen("iwconfig wlan0 \
                | grep 'ESSID' \
                | awk '{print $4}' \
                | awk -F\\\" '{print $2}'").read()
    return ssid
        
def get_network_info():
    ip = get_ip_address()
    ssid = get_wlan_ssid()
    return (f'wlan0: {ip}' if ip and ssid else 'wlan0: n/a').upper()

def main():
    create_pid_file()

    bus = smbus.SMBus(SM_BUS)
    time.sleep(1)

    chip = gpiod.Chip('gpiochip4')
    pld_line = chip.get_line(PLD_PIN)
    pld_line.request(consumer="PLD", type=gpiod.LINE_REQ_DIR_IN)

    while True:
        ac_power_state = pld_line.get_value()
        battery_info = get_battery_info(bus, ac_power_state)
        current_time, cpu_temp, cpu_usage, mem_usage = get_system_info()
        network_info = get_network_info()

        image = draw_display(current_time, cpu_temp, cpu_usage, mem_usage, battery_info, network_info)
        disp.show_image(disp.get_buffer(image))

        time.sleep(SLEEP_TIME_AC if ac_power_state else SLEEP_TIME_BAT)

if __name__ == "__main__":
    main()
