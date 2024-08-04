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
import requests
from dateutil import parser
from PIL import Image, ImageDraw, ImageFont


# Configure logging
#logging.basicConfig(level=logging.DEBUG)


# Constants
FONT_SIZE = 11
LEFT_PADDING = 1
SM_BUS = 1
PLD_PIN = 6
ADDRESS = 0x36
SLEEP_TIME_AC = 1
SLEEP_TIME_BAT = 10


BAT_THRESHOLD_HIGH = 70
BAT_THRESHOLD_MEDIUM = 50
BAT_THRESHOLD_LOW = 30
BAT_THRESHOLD_CRIT = 15


BYTES_IN_GYGABYTES = 1024.0 ** 3


DISPLAY_WIDTH = 128
DISPLAY_HEIGHT = 64


HOSTNAME = 'www.dmytrobezkrovnyi.com'


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


def get_battery_info(ac_power_state, capacity):
    """Return a formatted string with battery capacity and power state."""
    return f'{"+" if ac_power_state == 1 else "-"}{capacity}%{get_battery_capacity_label(capacity)}'


def get_cpu_temp():
    """CPU temperature."""
    cpu_temp = subprocess.check_output(['vcgencmd', 'measure_temp']).decode("utf-8").strip().replace('temp=', 't: ')
    return cpu_temp


def get_cpu_usage():
    """CPU usage."""
    cpu_usage = psutil.cpu_percent(interval=None)
    return f'CPU: {cpu_usage}%'


def get_mem_usage():
    """Fetch memory usage."""
    return psutil.virtual_memory().percent


def get_mem_info():
    """Fetch memory usage."""
    memory = psutil.virtual_memory()
    used_memory = round(memory.used / BYTES_IN_GYGABYTES, 1)
    used_memory_percent = round(memory.percent, 1)
    free_memory = round(memory.free / BYTES_IN_GYGABYTES, 1)
    return f'MEM: {used_memory}G / {used_memory_percent}% / {free_memory}G'


def get_disk_info():
    all_info = psutil.disk_usage('/')
    total_space = int(all_info.total / BYTES_IN_GYGABYTES)
    used_space = round(all_info.used / BYTES_IN_GYGABYTES, 1)
    used_space_percent = round(all_info.percent, 1)
    return f'SSD: {used_space}G / {used_space_percent}% / {total_space}G'


def draw_display_by_lines(lines):
    """Draw system information on the OLED display."""
    image = Image.new(mode='1', size=(DISPLAY_WIDTH, DISPLAY_HEIGHT), color="WHITE")
    draw = ImageDraw.Draw(image)
    if lines:
        for index, line in enumerate(lines):
            draw.text((LEFT_PADDING, index * FONT_SIZE), line.upper(), font=font)
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


def validate_ip(s):
    a = s.split('.')
    if len(a) != 4:
        return False
    for x in a:
        if not x.isdigit():
            return False
        i = int(x)
        if i < 0 or i > 255:
            return False
    return True


def is_host_pingable(host):
    try:
        response = requests.get("https://" + host)
        return response.status_code == 200
    except requests.ConnectionError:
        return False


def replace_ip(ip):
    if not ip or ip.count('.') <= 0:
        return ''
    parts = ip.split('.')
    return f'*.*.{parts[2]}.{parts[3]}'


def get_network_info():
    connection_status = replace_ip(psutil.net_if_addrs()["eth0"][0].address) if psutil.net_if_stats()['eth0'].isup else 'n/a'
    www_status = u'\u2713' if is_host_pingable(HOSTNAME) else 'X'
    return (f'eth0: {connection_status} | www: {www_status}')


def get_script_info(process):
    # Get memory usage in bytes
    memory_usage = process.memory_info().rss
    # Get CPU usage in percentage
    cpu_usage = process.cpu_percent(interval=None)  # interval can be adjusted
    return f'M: {memory_usage / (1024 * 1024):.1f} MB | CPU: {cpu_usage}%'


def get_battery_capacity_label(value):
    match value:
        case _ if value >= BAT_THRESHOLD_HIGH:
            return "H"
        case _ if value < BAT_THRESHOLD_HIGH and value >= BAT_THRESHOLD_MEDIUM:
            return "M"
        case _ if value < BAT_THRESHOLD_MEDIUM and value >= BAT_THRESHOLD_LOW:
            return "L"
        case _ if value < BAT_THRESHOLD_LOW and value >= BAT_THRESHOLD_CRIT:
            return "C"
    return "!!"


def check_shutdown_status(ac_status, battery_capacity):
    return (ac_status != 1 and BAT_THRESHOLD_LOW > battery_capacity >= BAT_THRESHOLD_CRIT)


def make_shutdown(ac_power_state, capacity):
    logging.error(f"{get_current_datetime()}: AC {ac_power_state} battery capacity is {capacity}, performing a shutdown...")
    disp.module_exit()
    os.system("shutdown now -h")
    sys.exit()
    exit()


def get_current_datetime():
    date_str = subprocess.check_output(['sudo', 'hwclock', '-r'])
    if date_str:
        # Преобразование строки в объект datetime
        date_obj = parser.parse(date_str)
        # Преобразование объекта datetime в строку с нужным форматом
        return date_obj.strftime('%d-%m-%y %H:%M')
    return datetime.datetime.now().strftime('%d-%m-%y %H:%M')


def main():
    try:
        create_pid_file()
        bus = smbus.SMBus(SM_BUS)
        time.sleep(1)

        chip = gpiod.Chip('gpiochip4')
        pld_line = chip.get_line(PLD_PIN)
        pld_line.request(consumer="PLD", type=gpiod.LINE_REQ_DIR_IN)

        disk_usage = get_disk_info()

        while True:
            ac_power_state = pld_line.get_value()
            capacity = int(read_capacity(bus))
            if check_shutdown_status(ac_power_state, capacity) == True:
                make_shutdown(ac_power_state, capacity)
            battery_info = get_battery_info(ac_power_state, capacity)
            current_time = get_current_datetime()
            cpu_temp = get_cpu_temp()
            cpu_usage = get_cpu_usage()
            mem_usage = get_mem_info()
            network_info = get_network_info()

            lines = [
                f'{current_time} | {battery_info}',
                f'{cpu_usage} | {cpu_temp}',
                mem_usage,
                disk_usage,
                network_info,
            ]

            image = draw_display_by_lines(lines)
            disp.show_image(disp.get_buffer(image))
            time.sleep(SLEEP_TIME_AC if ac_power_state else SLEEP_TIME_BAT)
    except IOError as e:
        logging.error(f"IOError: {e}")
    except KeyboardInterrupt:
        disp.module_exit()
        sys.exit()

if __name__ == "__main__":
    main()
