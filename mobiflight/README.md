# MobiFlight profiles (MobiFlight 9.7, X-Plane 11)

| File | Aircraft |
|---|---|
| `General.mcc` | All default aircraft except the 737: Cessna Skyhawk (+G1000), Baron 58, King Air C90, Cirrus SF50, Columbia 400, 747-100/-400, MD-82 |
| `Boeing_737.mcc` | Boeing 737-800 (`laminar/B738/...` datarefs) |
| `*.mfmc` | Board (pin) configs for the three Arduino Mega 2560 panels |

Open the profile matching the aircraft in MobiFlight (File > Open) before pressing Run.

`General.mcc` needs the FlyWithLua NG plugin and `../xplane/FlyWithLua/Scripts/mobiflight_starter.lua`
copied to `X-Plane 11/Resources/plugins/FlyWithLua/Scripts/` for the START position of the
magneto selector to hold the starter.
