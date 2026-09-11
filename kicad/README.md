# Guillotine filament-cutter controller

This KiCad 10 project contains the schematic for a compact 24 V electronic
filament-cutter controller. Every purchased component has a PCB footprint and
an `LCSC Part` field; `JP1` is intentionally bare PCB copper.

## Architecture

- `J1` accepts 24 V through JST-XH. `D1` is an SMBJ24A input TVS.
- `U2` (AP63205WU-7) generates 5 V at up to 2 A; `U3` (AMS1117-3.3)
  generates the digital 3.3 V rail. `L2` filters a separate analog 3.3 V rail.
- `U1` is an STM32F072C8T6 in LQFP-48, with an 8 MHz crystal, reset and BOOT0
  buttons, native USB DFU, and a dedicated SWD header.
- `U4` (DRV8870DDAR) drives the 24 V brushed motor. Its 50 mOhm low-side shunt
  sets a 2.2 A hardware current limit and is also measured by `U5`
  (INA180A1), producing 1.0 V/A at `PA0`.
- `U6` is an MT9105ET analog Hall sensor read on `PA1`.
- `U8` (SN65HVD230DR) provides 3.3 V CAN with NUP2105L bus protection.
  Closing `JP1` places `R13`, 120 ohms, across CANH and CANL.
- `U9` (SN74AHCT1G125DBVR) is a genuine TTL-input 3.3-to-5 V level translator
  for the chain of eight edge-mounted WS2812B-2020 RGB LEDs.
- `J5` and `J6` expose separate I2C and SPI buses on solderable headers.

## MCU pin allocation

| Function | STM32 pin |
| --- | --- |
| Motor IN1 / IN2 | PB0 / PB1 |
| Current / Hall ADC | PA0 / PA1 |
| USB D- / D+ | PA11 / PA12 |
| CAN RX / TX | PB8 / PB9 |
| I2C1 SCL / SDA | PB6 / PB7 |
| SPI1 CS / SCK / MISO / MOSI | PA4 / PA5 / PA6 / PA7 |
| NeoPixel data | PA8 |
| SWDIO / SWCLK | PA13 / PA14 |

USB VBUS powers only the USB ESD-protection reference. It is deliberately not
connected to the board's 5 V rail, so plugging in USB cannot back-power the
24 V-powered controller.

The AP63205 is rated for operation only up to 32 V input. The SMBJ24A is pulse
protection for a nominal 24 V rail; it is not a substitute for a regulated 24 V
supply and does not make sustained overvoltage safe.

## PCB layout notes

- Put `D3` through `D10` along the intended visible board edge. Place each
  100 nF bypass capacitor directly beside its LED.
- Route the buck converter input-capacitor, switch-node, inductor, and output-
  capacitor loops first and keep the switch node away from the Hall/ADC nets.
- Use Kelvin connections from both pads of `R5` to `U4`/`U5`. Keep the shunt
  ground return out of the MCU and Hall-sensor ground path.
- Use the specified thermal-via footprint beneath `U4`; connect its exposed pad
  to a generous ground copper area.
- Route USB D+/D- as a short, coupled 90-ohm differential pair. Place `U7` next
  to `J4`. Keep the crystal and its load capacitors tight to `U1`.
- Place `D2`, `R13`, and `JP1` close to the CAN connector. Close `JP1` only when
  this board is at an end of the CAN bus.
- The AMS1117 dissipates `(5 V - 3.3 V) * I3V3`; provide copper area and verify
  its temperature against the final LED-off logic load.

## Regeneration and verification

The checked-in `guillotine-pcb.kicad_sch` is the deliverable. The accompanying
generator requires Python 3, SKiDL 2.3, and the KiCad 10 libraries installed at
the standard macOS application path:

```sh
python generate_schematic.py
```

The final schematic was parsed and exported with KiCad 10.0.4. Error-severity
ERC is clean. KiCad's full ERC reports only library-symbol mismatch warnings
caused by SKiDL's embedded symbol copies differing from the locally installed
library cache; the electrical connections were separately audited from the
exported KiCad netlist.

LCSC identifiers are a sourcing snapshot dated 2026-09-10. Recheck price,
stock, lifecycle, and exact parametric suitability before ordering.
