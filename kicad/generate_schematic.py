#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) jrlomas
"""Generate the guillotine controller schematic with SKiDL/KiCad 10 libraries.

The checked-in .kicad_sch is the deliverable.  This source is kept so that
net assignments, footprints, and LCSC selections remain easy to audit.
"""

from __future__ import annotations

import os
import importlib
import builtins
import subprocess
from pathlib import Path


KICAD_ROOT = Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport")
KICAD_CLI = Path("/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli")
SYMBOL_DIR = KICAD_ROOT / "symbols"
FOOTPRINT_DIR = KICAD_ROOT / "footprints"

os.environ.setdefault("KICAD_SYMBOL_DIR", str(SYMBOL_DIR))
for version in (6, 7, 8, 9, 10):
    os.environ.setdefault(f"KICAD{version}_SYMBOL_DIR", str(SYMBOL_DIR))
os.environ.setdefault("KICAD10_FOOTPRINT_DIR", str(FOOTPRINT_DIR))
os.environ.setdefault("MPLCONFIGDIR", "/tmp/guillotine-skidl-mpl")

from skidl import (  # noqa: E402
    KICAD10,
    Group,
    POWER,
    Part,
    Net,
    generate_schematic,
    set_default_tool,
)
from skidl.net import NCNet  # noqa: E402


set_default_tool(KICAD10)

# With a label-only drawing, SKiDL's two-pin snap pass is counterproductive:
# it may insert a residual wire between nearby power pins after those nets have
# already been classified as stubs.  Disable that pass so every connection is
# represented only by its unambiguous global label.
kicad10_generator = importlib.import_module("skidl.tools.kicad10.gen_schematic")
kicad10_generator._snap_two_pin_parts = lambda node: None


def component(
    lib: str,
    name: str,
    ref: str,
    *,
    value: str | None = None,
    footprint: str | None = None,
    lcsc: str | None = None,
    mpn: str | None = None,
) -> Part:
    """Create a part and attach the sourcing fields used by the BOM."""
    kwargs = {"ref": ref}
    if value is not None:
        kwargs["value"] = value
    if footprint is not None:
        kwargs["footprint"] = footprint
    part = Part(lib, name, tool=KICAD10, **kwargs)
    if lcsc:
        part.fields["LCSC Part"] = lcsc
    if mpn:
        part.fields["Manufacturer Part"] = mpn
    return part


def resistor(ref: str, value: str, lcsc: str, *, size: str = "0402") -> Part:
    metric = {
        "0402": "0402_1005Metric",
        "0603": "0603_1608Metric",
        "1206": "1206_3216Metric",
        "2512": "2512_6332Metric",
    }[size]
    return component(
        "Device",
        "R_Small",
        ref,
        value=value,
        footprint=f"Resistor_SMD:R_{metric}",
        lcsc=lcsc,
    )


def capacitor(
    ref: str,
    value: str,
    lcsc: str,
    *,
    size: str = "0402",
    polarized: bool = False,
) -> Part:
    if polarized:
        return component(
            "Device",
            "C_Polarized_Small",
            ref,
            value=value,
            footprint="Capacitor_SMD:CP_Elec_6.3x7.7",
            lcsc=lcsc,
        )
    metric = {
        "0402": "0402_1005Metric",
        "0603": "0603_1608Metric",
        "0805": "0805_2012Metric",
        "1206": "1206_3216Metric",
    }[size]
    return component(
        "Device",
        "C_Small",
        ref,
        value=value,
        footprint=f"Capacitor_SMD:C_{metric}",
        lcsc=lcsc,
    )


def connect_cap(cap: Part, rail: Net, gnd: Net) -> None:
    rail += cap[1]
    gnd += cap[2]


def no_connect_unused(part: Part) -> None:
    """Place explicit no-connect markers on every still-unused pin."""
    unused = [pin for pin in part.pins if not pin.is_connected()]
    if unused:
        nc = NCNet(f"{part.ref}_UNUSED")
        nc += unused


# Named nets are deliberately used throughout.  The generated drawing places
# matching labels at pins, keeping a dense one-sheet schematic unambiguous.
# Use explicit global-label names instead of KiCad's power-symbol aliases.
# This keeps every rail connection mechanically identical in the generated
# drawing and avoids orientation-dependent power-symbol placement.
gnd = Net("GND_0V")
v24 = Net("24V_RAW")
v5 = Net("5V_SYS")
v33 = Net("3V3_SYS")
v33a = Net("3V3_ANALOG")
for rail in (gnd, v24, v5, v33, v33a):
    rail.drive = POWER

# KiCad ERC needs explicit power-output sources for connector-fed rails and
# regulator outputs.  These symbols are schematic-only and never enter the BOM.
for rail in (gnd, v24, v5, v33a):
    pwr_flag = Part("power", "PWR_FLAG", tool=KICAD10)
    rail += pwr_flag[1]


# ---------------------------------------------------------------------------
# 24 V entry, 5 V synchronous buck, and 3.3 V LDO.
# ---------------------------------------------------------------------------
j1 = component(
    "Connector_Generic",
    "Conn_01x02",
    "J1",
    value="24V POWER (JST-XH)",
    footprint="Connector_JST:JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical",
    lcsc="C158012",
    mpn="B2B-XH-A(LF)(SN)",
)
v24 += j1[1]
gnd += j1[2]

d1 = component(
    "Device",
    "D_TVS",
    "D1",
    value="SMBJ24A",
    footprint="Diode_SMD:D_SMB",
    lcsc="C123819",
    mpn="SMBJ24A",
)
v24 += d1[1]
gnd += d1[2]

c1 = capacitor("C1", "47uF 35V", "C424110", polarized=True)
connect_cap(c1, v24, gnd)

u2 = component(
    "Regulator_Switching",
    "AP63205WU",
    "U2",
    value="AP63205WU-7 (5V/2A)",
    footprint="Package_TO_SOT_SMD:TSOT-23-6",
    lcsc="C2071056",
    mpn="AP63205WU-7",
)
v24 += u2[2, 3]  # EN and IN.
gnd += u2[4]
v5 += u2[1]  # Fixed-output FB sense.
buck_sw = Net("BUCK_SW")
buck_bst = Net("BUCK_BST")
buck_sw += u2[5]
buck_bst += u2[6]

l1 = component(
    "Device",
    "L_Small",
    "L1",
    value="4.7uH >=3A",
    footprint="Inductor_SMD:L_Taiyo-Yuden_NR-60xx",
    lcsc="C42428085",
    mpn="ZENR6028T4R7M-4.7uH",
)
buck_sw += l1[1]
v5 += l1[2]

c2 = capacitor("C2", "100nF BST", "C1525")
buck_bst += c2[1]
buck_sw += c2[2]
c3 = capacitor("C3", "10uF 50V", "C13585", size="1206")
connect_cap(c3, v24, gnd)
for ref in ("C4", "C5"):
    connect_cap(capacitor(ref, "22uF 10V", "C45783", size="0805"), v5, gnd)

u3 = component(
    "Regulator_Linear",
    "AMS1117-3.3",
    "U3",
    value="AMS1117-3.3",
    footprint="Package_TO_SOT_SMD:SOT-223-3_TabPin2",
    lcsc="C6186",
    mpn="AMS1117-3.3",
)
gnd += u3[1]
v33 += u3[2]
v5 += u3[3]
connect_cap(capacitor("C6", "22uF 10V", "C45783", size="0805"), v5, gnd)
connect_cap(capacitor("C7", "22uF 10V", "C45783", size="0805"), v33, gnd)
connect_cap(capacitor("C8", "100nF", "C1525"), v33, gnd)

l2 = component(
    "Device",
    "L_Small",
    "L2",
    value="120R @ 100MHz ferrite",
    footprint="Inductor_SMD:L_0603_1608Metric",
    lcsc="C113030",
    mpn="BLM18SG121TN1D",
)
v33 += l2[1]
v33a += l2[2]
connect_cap(capacitor("C9", "1uF", "C52923"), v33a, gnd)
connect_cap(capacitor("C10", "100nF", "C1525"), v33a, gnd)


# ---------------------------------------------------------------------------
# MCU, clock, reset/boot controls, and factory SWD header.
# ---------------------------------------------------------------------------
u1 = component(
    "MCU_ST_STM32F0",
    "STM32F072C8Tx",
    "U1",
    value="STM32F072C8T6",
    footprint="Package_QFP:LQFP-48_7x7mm_P0.5mm",
    lcsc="C80488",
    mpn="STM32F072C8T6",
)
v33 += u1[1, 24, 36, 48]  # VBAT, VDD, VDDIO2, VDD.
v33a += u1[9]  # VDDA.
gnd += u1[8, 23, 35, 47]  # VSSA and VSS pins.
for ref in ("C11", "C12", "C13", "C14"):
    connect_cap(capacitor(ref, "100nF", "C1525"), v33, gnd)

osc_in = Net("OSC_IN_8MHZ")
osc_out = Net("OSC_OUT_8MHZ")
osc_in += u1[5]
osc_out += u1[6]
y1 = component(
    "Device",
    "Crystal_GND24_Small",
    "Y1",
    value="8MHz 20pF",
    footprint="Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm",
    lcsc="C2682774",
    mpn="X32258MSB4SI",
)
osc_in += y1[1]
osc_out += y1[3]
gnd += y1[2, 4]
c15 = capacitor("C15", "33pF", "C1562")
c16 = capacitor("C16", "33pF", "C1562")
osc_in += c15[1]
osc_out += c16[1]
gnd += c15[2], c16[2]

nrst = Net("NRST")
boot0 = Net("BOOT0")
nrst.stub = True
boot0.stub = True
nrst += u1[7]
boot0 += u1[44]
r1 = resistor("R1", "10k", "C25744")
v33 += r1[1]
nrst += r1[2]
c17 = capacitor("C17", "100nF", "C1525")
nrst += c17[1]
gnd += c17[2]
sw1 = component(
    "Switch",
    "SW_Push",
    "SW1",
    value="RESET",
    footprint="Button_Switch_SMD:SW_SPST_PTS810",
    lcsc="C221895",
    mpn="PTS810SJG250SMTRLFS",
)
nrst += sw1[1]
gnd += sw1[2]
r2 = resistor("R2", "10k BOOT0 pull-down", "C25744")
boot0 += r2[1]
gnd += r2[2]
sw2 = component(
    "Switch",
    "SW_Push",
    "SW2",
    value="BOOT/DFU",
    footprint="Button_Switch_SMD:SW_SPST_PTS810",
    lcsc="C221895",
    mpn="PTS810SJG250SMTRLFS",
)
v33 += sw2[1]
boot0 += sw2[2]

swdio = Net("SWDIO")
swclk = Net("SWCLK")
swdio.stub = True
swclk.stub = True
swdio += u1[34]  # PA13.
swclk += u1[37]  # PA14.
j7 = component(
    "Connector_Generic",
    "Conn_01x05",
    "J7",
    value="SWD PROGRAM HEADER",
    footprint="Connector_PinHeader_1.27mm:PinHeader_1x05_P1.27mm_Vertical",
    lcsc="C22438102",
    mpn="HX PZ1.27-1x5P ZZ",
)
v33 += j7[1]
swdio += j7[2]
swclk += j7[3]
nrst += j7[4]
gnd += j7[5]


# ---------------------------------------------------------------------------
# 24 V brushed-DC H-bridge and low-side shunt current measurement.
# The DRV8870 trip point is 1.1 V / (10 * 0.05 ohm) = 2.2 A.
# INA180A1 output scaling is 20 * 0.05 ohm = 1.0 V/A.
# ---------------------------------------------------------------------------
motor_in1 = Net("MOTOR_IN1_PWM")
motor_in2 = Net("MOTOR_IN2_PWM")
motor_in1.stub = True
motor_in2.stub = True
motor_in1 += u1[18]  # PB0 / TIM3_CH3.
motor_in2 += u1[19]  # PB1 / TIM3_CH4.

u4 = component(
    "Driver_Motor",
    "DRV8870DDA",
    "U4",
    value="DRV8870DDAR 3.6A H-bridge",
    footprint=(
        "Package_SO:Texas_HTSOP-8-1EP_3.9x4.9mm_P1.27mm_"
        "EP2.95x4.9mm_Mask2.4x3.1mm_ThermalVias"
    ),
    lcsc="C86590",
    mpn="DRV8870DDAR",
)
gnd += u4[1, 9]
motor_in2 += u4[2]
motor_in1 += u4[3]
v24 += u4[5]
motor_out1 = Net("MOTOR_OUT1")
motor_out2 = Net("MOTOR_OUT2")
motor_out1 += u4[6]
motor_out2 += u4[8]

motor_vref = Net("MOTOR_VREF_1V1")
motor_isense = Net("MOTOR_ISENSE_SHUNT")
motor_vref += u4[4]
motor_isense += u4[7]
r3 = resistor("R3", "20k", "C25765")
r4 = resistor("R4", "10k", "C25744")
v33 += r3[1]
motor_vref += r3[2], r4[1]
gnd += r4[2]
c18 = capacitor("C18", "10nF VREF filter", "C15195")
motor_vref += c18[1]
gnd += c18[2]
r5 = resistor("R5", "0.05R 3W shunt", "C500743", size="2512")
motor_isense += r5[1]
gnd += r5[2]

j2 = component(
    "Connector_Generic",
    "Conn_01x02",
    "J2",
    value="DC MOTOR (JST-XH)",
    footprint="Connector_JST:JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical",
    lcsc="C158012",
    mpn="B2B-XH-A(LF)(SN)",
)
motor_out1 += j2[1]
motor_out2 += j2[2]
connect_cap(capacitor("C19", "100nF 50V", "C14663", size="0603"), v24, gnd)
connect_cap(capacitor("C20", "47uF 35V", "C424110", polarized=True), v24, gnd)

u5 = component(
    "Amplifier_Current",
    "INA180A1",
    "U5",
    value="INA180A1IDBVR (20V/V)",
    footprint="Package_TO_SOT_SMD:SOT-23-5",
    lcsc="C122228",
    mpn="INA180A1IDBVR",
)
gnd += u5[2, 4]
motor_isense += u5[3]
v33 += u5[5]
current_raw = Net("MOTOR_CURRENT_RAW")
current_adc = Net("MOTOR_CURRENT_ADC_1V_PER_A")
current_adc.stub = True
current_raw += u5[1]
r6 = resistor("R6", "1k ADC filter", "C11702")
current_raw += r6[1]
current_adc += r6[2]
c21 = capacitor("C21", "100nF ADC filter", "C1525")
current_adc += c21[1]
gnd += c21[2]
current_adc += u1[10]  # PA0 / ADC_IN0.
connect_cap(capacitor("C22", "100nF", "C1525"), v33, gnd)


# ---------------------------------------------------------------------------
# Analog Hall-effect position sensor.
# A1301xLH has the same VCC/VOUT/GND pin order as MT9105ET.
# ---------------------------------------------------------------------------
u6 = component(
    "Sensor_Magnetic",
    "A1301xLH",
    "U6",
    value="MT9105ET analog Hall 5mV/G",
    footprint="Package_TO_SOT_SMD:SOT-23",
    lcsc="C967861",
    mpn="MT9105ET",
)
v33 += u6[1]
gnd += u6[3]
hall_raw = Net("HALL_RAW")
hall_adc = Net("HALL_ADC")
hall_adc.stub = True
hall_raw += u6[2]
r7 = resistor("R7", "1k ADC filter", "C11702")
hall_raw += r7[1]
hall_adc += r7[2]
c23 = capacitor("C23", "100nF ADC filter", "C1525")
hall_adc += c23[1]
gnd += c23[2]
hall_adc += u1[11]  # PA1 / ADC_IN1.
connect_cap(capacitor("C24", "100nF", "C1525"), v33, gnd)


# ---------------------------------------------------------------------------
# USB-C full-speed device port for the STM32 ROM DFU bootloader.
# USB VBUS is intentionally not tied to the board's +5 V rail.
# ---------------------------------------------------------------------------
j4 = component(
    "Connector",
    "USB_C_Receptacle_USB2.0_16P",
    "J4",
    value="USB-C PROGRAM/DFU",
    footprint="Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12",
    lcsc="C165948",
    mpn="TYPE-C-31-M-12",
)
usb_vbus = Net("USB_VBUS")
usb_dp_conn = Net("USB_DP_CONN")
usb_dm_conn = Net("USB_DM_CONN")
usb_dp_esd = Net("USB_DP_ESD")
usb_dm_esd = Net("USB_DM_ESD")
usb_dp = Net("USB_DP_PA12")
usb_dm = Net("USB_DM_PA11")
for net in (usb_vbus, usb_dp, usb_dm):
    net.stub = True
usb_vbus += j4["A4", "A9", "B4", "B9"]
gnd += j4["A1", "A12", "B1", "B12", "SH"]
usb_dp_conn += j4["A6", "B6"]
usb_dm_conn += j4["A7", "B7"]
r8 = resistor("R8", "5.1k CC1", "C25905")
r9 = resistor("R9", "5.1k CC2", "C25905")
j4["A5"] += r8[1]
j4["B5"] += r9[1]
gnd += r8[2], r9[2]

u7 = component(
    "Power_Protection",
    "USBLC6-2SC6",
    "U7",
    value="USBLC6-2SC6 USB ESD",
    footprint="Package_TO_SOT_SMD:SOT-23-6",
    lcsc="C7519",
    mpn="USBLC6-2SC6",
)
usb_dp_conn += u7[1]
usb_dp_esd += u7[6]
usb_dm_conn += u7[3]
usb_dm_esd += u7[4]
gnd += u7[2]
usb_vbus += u7[5]
r10 = resistor("R10", "22R USB D+", "C25092")
r11 = resistor("R11", "22R USB D-", "C25092")
usb_dp_esd += r10[1]
usb_dp += r10[2]
usb_dm_esd += r11[1]
usb_dm += r11[2]
usb_dp += u1[33]
usb_dm += u1[32]
no_connect_unused(j4)  # SBU1/SBU2.


# ---------------------------------------------------------------------------
# 3.3 V CAN transceiver, connector protection, and solder-jumper termination.
# ---------------------------------------------------------------------------
can_tx = Net("CAN_TX_PB9")
can_rx = Net("CAN_RX_PB8")
can_h = Net("CAN_H")
can_l = Net("CAN_L")
for net in (can_tx, can_rx, can_h, can_l):
    net.stub = True
can_tx += u1[46]
can_rx += u1[45]

u8 = component(
    "Interface_CAN_LIN",
    "SN65HVD230",
    "U8",
    value="SN65HVD230DR 3.3V CAN",
    footprint="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
    lcsc="C12084",
    mpn="SN65HVD230DR",
)
can_tx += u8[1]
gnd += u8[2]
v33 += u8[3]
can_rx += u8[4]
can_l += u8[6]
can_h += u8[7]
r12 = resistor("R12", "0R high-speed CAN", "C17168")
u8[8] += r12[1]
gnd += r12[2]
no_connect_unused(u8)  # Vref is not needed.
connect_cap(capacitor("C25", "100nF", "C1525"), v33, gnd)

d2 = component(
    "Power_Protection",
    "NUP2105L",
    "D2",
    value="NUP2105L CAN TVS",
    footprint="Package_TO_SOT_SMD:SOT-23",
    lcsc="C284104",
    mpn="NUP2105L",
)
gnd += d2[3]
can_h += d2[1]
can_l += d2[2]
j3 = component(
    "Connector_Generic",
    "Conn_01x03",
    "J3",
    value="CAN (JST-XH)",
    footprint="Connector_JST:JST_XH_B3B-XH-A_1x03_P2.50mm_Vertical",
    lcsc="C144394",
    mpn="B3B-XH-A(LF)(SN)",
)
can_h += j3[1]
can_l += j3[2]
gnd += j3[3]
r13 = resistor("R13", "120R CAN TERM", "C17909", size="1206")
can_h += r13[1]
can_term = Net("CAN_TERM_JUMPER")
can_term += r13[2]
jp1 = component(
    "Jumper",
    "Jumper_2_Open",
    "JP1",
    value="SOLDER CLOSED = 120R CAN TERM",
    footprint="Jumper:SolderJumper-2_P1.3mm_Open_RoundedPad1.0x1.5mm",
)
jp1.fields["BOM Note"] = "PCB copper; no purchased part"
can_term += jp1[1]
can_l += jp1[2]


# ---------------------------------------------------------------------------
# Eight edge NeoPixels with a real 5 V TTL-compatible level translator.
# A BSS138-style bidirectional MOSFET shifter is not used because NeoPixel DIN
# is push-pull, not open drain.
# ---------------------------------------------------------------------------
neopixel_mcu = Net("NEOPIXEL_DATA_PA8_3V3")
neopixel_5v = Net("NEOPIXEL_DATA_5V")
neopixel_mcu.stub = True
neopixel_5v.stub = True
neopixel_mcu += u1[29]
u9 = component(
    "74xGxx",
    "74AHCT1G125",
    "U9",
    value="SN74AHCT1G125DBVR",
    footprint="Package_TO_SOT_SMD:SOT-23-5",
    lcsc="C7484",
    mpn="SN74AHCT1G125DBVR",
)
gnd += u9[1, 3]  # /OE asserted and ground.
neopixel_mcu += u9[2]
v5 += u9[5]
neopixel_buffer_out = Net("NEOPIXEL_BUFFER_OUT")
neopixel_buffer_out += u9[4]
r14 = resistor("R14", "33R NeoPixel data", "C25105")
neopixel_buffer_out += r14[1]
neopixel_5v += r14[2]
connect_cap(capacitor("C26", "100nF", "C1525"), v5, gnd)

previous_data = neopixel_5v
for index, ref in enumerate(("D3", "D4", "D5", "D6", "D7", "D8", "D9", "D10"), 1):
    led = component(
        "LED",
        "WS2812B-2020",
        ref,
        value="WS2812B-2020 EDGE",
        footprint="LED_SMD:LED_WS2812B-2020_PLCC4_2.0x2.0mm",
        lcsc="C965555",
        mpn="WS2812B-2020",
    )
    previous_data += led[3]
    v5 += led[4]
    gnd += led[2]
    connect_cap(capacitor(f"C{26 + index}", "100nF", "C1525"), v5, gnd)
    if index < 8:
        next_data = Net(f"NEOPIXEL_D{index}_TO_D{index + 1}")
        next_data.stub = True
        next_data += led[1]
        previous_data = next_data
    else:
        nc_led = NCNet("NEOPIXEL_CHAIN_END")
        nc_led += led[1]


# ---------------------------------------------------------------------------
# Separate, solderable I2C and SPI headers.
# ---------------------------------------------------------------------------
i2c_scl = Net("I2C1_SCL_PB6")
i2c_sda = Net("I2C1_SDA_PB7")
spi_sck = Net("SPI1_SCK_PA5")
spi_miso = Net("SPI1_MISO_PA6")
spi_mosi = Net("SPI1_MOSI_PA7")
spi_cs = Net("SPI1_CS_PA4")
for net in (i2c_scl, i2c_sda, spi_sck, spi_miso, spi_mosi, spi_cs):
    net.stub = True
i2c_scl += u1[42]
i2c_sda += u1[43]
spi_cs += u1[14]
spi_sck += u1[15]
spi_miso += u1[16]
spi_mosi += u1[17]

r15 = resistor("R15", "4.7k I2C SCL pull-up", "C25900")
r16 = resistor("R16", "4.7k I2C SDA pull-up", "C25900")
v33 += r15[1], r16[1]
i2c_scl += r15[2]
i2c_sda += r16[2]
j5 = component(
    "Connector_Generic",
    "Conn_01x04",
    "J5",
    value="I2C SOLDERABLE HEADER",
    footprint="Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical",
    lcsc="C124378",
    mpn="B-2100S04P-A110",
)
v33 += j5[1]
gnd += j5[2]
i2c_scl += j5[3]
i2c_sda += j5[4]

j6 = component(
    "Connector_Generic",
    "Conn_01x06",
    "J6",
    value="SPI SOLDERABLE HEADER",
    footprint="Connector_PinHeader_2.54mm:PinHeader_1x06_P2.54mm_Vertical",
    lcsc="C124380",
    mpn="B-2100S06P-A110",
)
v33 += j6[1]
gnd += j6[2]
spi_sck += j6[3]
spi_mosi += j6[4]
spi_miso += j6[5]
spi_cs += j6[6]


# Every unallocated MCU GPIO is explicitly intentional, not an ERC accident.
no_connect_unused(u1)


# Group the already-connected parts for functional block placement.  Keeping
# this hierarchy flattened produces one editable sheet while giving the
# autoplacer the same organization an engineer would use by hand.
group_refs = {
    "POWER": {
        "J1", "D1", "C1", "U2", "L1", "C2", "C3", "C4", "C5",
        "U3", "C6", "C7", "C8", "L2", "C9", "C10",
    },
    "MCU_CLOCK_PROGRAM": {
        "U1", "C11", "C12", "C13", "C14", "Y1", "C15", "C16",
        "R1", "C17", "SW1", "R2", "SW2", "J7",
    },
    "MOTOR_CURRENT": {
        "U4", "R3", "R4", "C18", "R5", "J2", "C19", "C20",
        "U5", "R6", "C21", "C22",
    },
    "HALL_POSITION": {"U6", "R7", "C23", "C24"},
    "USB_DFU": {"J4", "R8", "R9", "U7", "R10", "R11"},
    "CAN_BUS": {"U8", "R12", "C25", "D2", "J3", "R13", "JP1"},
    "EDGE_NEOPIXELS": {
        "U9", "R14", "C26", "D3", "D4", "D5", "D6", "D7", "D8",
        "D9", "D10", "C27", "C28", "C29", "C30", "C31", "C32",
        "C33", "C34",
    },
    "EXPANSION_HEADERS": {"R15", "R16", "J5", "J6"},
}

circuit = builtins.default_circuit
assigned_refs = set()
for group_name, refs in group_refs.items():
    group = Group(group_name, circuit=circuit)
    with group:
        pass
    for part in circuit.parts:
        if part.ref in refs or (group_name == "POWER" and part.ref.startswith("#FLG")):
            if part in circuit.root.parts:
                circuit.root.parts.remove(part)
            group.parts.append(part)
            part.node = group
            assigned_refs.add(part.ref)

real_refs = {part.ref for part in circuit.parts if not part.ref.startswith("#FLG")}
missing_groups = real_refs - assigned_refs
if missing_groups:
    raise RuntimeError(f"Parts missing a functional placement group: {sorted(missing_groups)}")

generate_schematic(
    tool=KICAD10,
    filepath=str(Path(__file__).resolve().parent),
    top_name="guillotine-pcb",
    title="24 V Electronic Filament Cutter Controller",
    flatness=1.0,
    auto_stub=True,
    auto_stub_fanout=4,
    auto_stub_max_wire_pins=1,
    auto_stub_max_wire_dist=0,
    label_clearance=True,
    seed=42,
    erc_max_iterations=4,
    retries=3,
)

# Normalize SKiDL's output to the current KiCad 10 file revision.  This also
# makes the generated deliverable open without an upgrade prompt.
subprocess.run(
    [str(KICAD_CLI), "sch", "upgrade", "--force", "guillotine-pcb.kicad_sch"],
    cwd=Path(__file__).resolve().parent,
    check=True,
)
