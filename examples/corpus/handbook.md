---
title: Larkspur Field Handbook
---

# Larkspur Field Handbook

This handbook covers day-to-day operation of the Larkspur L2 delivery rover. It is written for field technicians at the fictional Larkspur Robotics depot.

## Daily checks

Before the first run of the day, walk around the rover and complete the checks below. A rover that fails any check stays in the depot.

- Tyres: no cuts, pressure between 28 and 32 psi
- Lidar dome: clean and free of scratches
- Cargo latch: closes with a single push

### Battery

The battery must show at least 80% before a rover leaves the depot. Charging from empty takes about 3 hours on a depot charger. Never charge a battery that is below 5 degrees Celsius; bring the rover indoors first and wait 30 minutes.

## Fault codes

| Code | Meaning | Action |
| --- | --- | --- |
| E12 | Wheel motor over temperature | Stop for 10 minutes, then resume |
| E27 | Lidar blocked | Clean the dome and restart |
| E40 | Cargo latch open | Close the latch; replace it if the code returns |

Report any code that is not in the table to depot-support@larkspur.example.com.

## Resetting the controller

```bash
rover-ctl stop
rover-ctl reset --keep-maps
rover-ctl start
```

A reset keeps stored maps but clears the fault history, so note the codes down first.
