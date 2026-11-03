"""Convert a MobiFlight 9.7 X-Plane profile (.mcc) to an MSFS 2020 profile.

X-Plane datarefs become SimConnect RPN code (A: simvars) and X-Plane commands
become MSFS events (K: events), using the tables below. Display settings,
modifiers, variables and preconditions are kept as they are, so the panels
behave the same in both simulators. Configs that have no MSFS equivalent, or
that duplicate another one in MSFS, are deactivated.

Usage: python xplane_to_msfs.py General.mcc MSFS_General.mcc
"""
import re
import sys
from xml.sax.saxutils import escape

# --- Outputs: X-Plane dataref -> SimConnect RPN code ---------------------------
# Values are scaled to the same units the X-Plane dataref used, so the existing
# transformations (e.g. $*0.001 on frequencies) keep working unchanged.
OUTPUTS = {
    '': '0',  # blank display line (shows ' ' through its comparison)
    'sim/cockpit/autopilot/altitude': '(A:AUTOPILOT ALTITUDE LOCK VAR,feet)',
    'sim/cockpit/autopilot/vertical_velocity': '(A:AUTOPILOT VERTICAL HOLD VAR,feet per minute)',
    'sim/cockpit/autopilot/airspeed': '(A:AUTOPILOT AIRSPEED HOLD VAR,knots)',
    'sim/cockpit2/autopilot/heading_dial_deg_mag_pilot': '(A:AUTOPILOT HEADING LOCK DIR,degrees)',
    'sim/cockpit/radios/nav1_course_degm': '(A:NAV OBS:1,degrees)',
    'sim/cockpit/radios/nav2_obs_degm2': '(A:NAV OBS:2,degrees)',
    # autopilot mode LEDs
    'sim/cockpit2/autopilot/servos_on': '(A:AUTOPILOT MASTER,bool)',
    'sim/cockpit2/autopilot/heading_status': '(A:AUTOPILOT HEADING LOCK,bool)',
    'sim/cockpit2/autopilot/nav_status': '(A:AUTOPILOT NAV1 LOCK,bool)',
    'sim/cockpit2/autopilot/altitude_hold_status': '(A:AUTOPILOT ALTITUDE LOCK,bool)',
    'sim/cockpit2/autopilot/vvi_status': '(A:AUTOPILOT VERTICAL HOLD,bool)',
    'sim/cockpit2/autopilot/approach_status': '(A:AUTOPILOT APPROACH HOLD,bool)',
    'sim/cockpit2/autopilot/speed_status': '(A:AUTOPILOT FLIGHT LEVEL CHANGE,bool) (A:AUTOPILOT AIRSPEED HOLD,bool) or',
    'sim/cockpit2/autopilot/backcourse_status': '(A:AUTOPILOT BACKCOURSE HOLD,bool)',
    # gear position 0..1 (1 = down and locked)
    'sim/flightmodel2/gear/deploy_ratio[0]': '(A:GEAR CENTER POSITION,percent over 100)',
    'sim/flightmodel2/gear/deploy_ratio[1]': '(A:GEAR LEFT POSITION,percent over 100)',
    'sim/flightmodel2/gear/deploy_ratio[2]': '(A:GEAR RIGHT POSITION,percent over 100)',
    # radios: COM/NAV in 10 kHz units like X-Plane (118.50 MHz -> 11850), ADF in kHz
    'sim/cockpit/radios/com1_freq_hz': '(A:COM ACTIVE FREQUENCY:1,KHz) 10 /',
    'sim/cockpit/radios/com2_freq_hz': '(A:COM ACTIVE FREQUENCY:2,KHz) 10 /',
    'sim/cockpit2/radios/actuators/com1_standby_frequency_hz': '(A:COM STANDBY FREQUENCY:1,KHz) 10 /',
    'sim/cockpit2/radios/actuators/com2_standby_frequency_hz': '(A:COM STANDBY FREQUENCY:2,KHz) 10 /',
    'sim/cockpit/radios/nav1_freq_hz': '(A:NAV ACTIVE FREQUENCY:1,KHz) 10 /',
    'sim/cockpit/radios/nav2_freq_hz': '(A:NAV ACTIVE FREQUENCY:2,KHz) 10 /',
    'sim/cockpit/radios/nav1_stdby_freq_hz': '(A:NAV STANDBY FREQUENCY:1,KHz) 10 /',
    'sim/cockpit2/radios/actuators/nav2_standby_frequency_hz': '(A:NAV STANDBY FREQUENCY:2,KHz) 10 /',
    'sim/cockpit/radios/adf1_freq_hz': '(A:ADF ACTIVE FREQUENCY:1,KHz)',
    'sim/cockpit/radios/adf1_stdby_freq_hz': '(A:ADF STANDBY FREQUENCY:1,KHz)',
    'sim/cockpit2/radios/indicators/nav1_dme_distance_nm': '(A:NAV DME:1,nautical miles)',
    'sim/cockpit/radios/transponder_code': '(A:TRANSPONDER CODE:1,number)',
    'sim/flightmodel2/controls/elevator_trim': '(A:ELEVATOR TRIM PCT,percent over 100)',
}

# --- Inputs: X-Plane command -> MSFS RPN code (None = no equivalent, deactivate) --
def toggle_to(state_var, event, want):
    """Turn a toggle-only event into a set: toggle only if the state differs."""
    cond = state_var if not want else state_var + ' !'
    return f'{cond} if{{ (>K:{event}) }}'

COMMANDS = {
    'sim/flight_controls/landing_gear_down': '(>K:GEAR_DOWN)',
    'sim/flight_controls/landing_gear_up': '(>K:GEAR_UP)',
    'sim/flight_controls/flaps_up': '(>K:FLAPS_DECR)',
    'sim/flight_controls/flaps_down': '(>K:FLAPS_INCR)',
    'sim/flight_controls/pitch_trim_up': '(>K:ELEV_TRIM_UP)',
    'sim/flight_controls/pitch_trim_down': '(>K:ELEV_TRIM_DN)',
    'sim/flight_controls/cowl_flaps_closed': '0 (>K:COWLFLAP1_SET) 0 (>K:COWLFLAP2_SET)',
    'sim/flight_controls/cowl_flaps_open': '16383 (>K:COWLFLAP1_SET) 16383 (>K:COWLFLAP2_SET)',
    # radios
    'sim/radios/stby_com1_coarse_down': '(>K:COM_RADIO_WHOLE_DEC)',
    'sim/radios/stby_com1_coarse_up': '(>K:COM_RADIO_WHOLE_INC)',
    'sim/radios/stby_com1_fine_down': '(>K:COM_RADIO_FRACT_DEC)',
    'sim/radios/stby_com1_fine_up': '(>K:COM_RADIO_FRACT_INC)',
    'sim/radios/stby_com2_coarse_down': '(>K:COM2_RADIO_WHOLE_DEC)',
    'sim/radios/stby_com2_coarse_up': '(>K:COM2_RADIO_WHOLE_INC)',
    'sim/radios/stby_com2_fine_down': '(>K:COM2_RADIO_FRACT_DEC)',
    'sim/radios/stby_com2_fine_up': '(>K:COM2_RADIO_FRACT_INC)',
    'sim/radios/stby_nav1_coarse_down': '(>K:NAV1_RADIO_WHOLE_DEC)',
    'sim/radios/stby_nav1_coarse_up': '(>K:NAV1_RADIO_WHOLE_INC)',
    'sim/radios/stby_nav1_fine_down': '(>K:NAV1_RADIO_FRACT_DEC)',
    'sim/radios/stby_nav1_fine_up': '(>K:NAV1_RADIO_FRACT_INC)',
    'sim/radios/stby_nav2_coarse_down': '(>K:NAV2_RADIO_WHOLE_DEC)',
    'sim/radios/stby_nav2_coarse_up': '(>K:NAV2_RADIO_WHOLE_INC)',
    'sim/radios/stby_nav2_fine_down': '(>K:NAV2_RADIO_FRACT_DEC)',
    'sim/radios/stby_nav2_fine_up': '(>K:NAV2_RADIO_FRACT_INC)',
    'sim/radios/stby_adf1_hundreds_thous_down': '(>K:ADF_100_DEC)',
    'sim/radios/stby_adf1_hundreds_thous_up': '(>K:ADF_100_INC)',
    'sim/radios/stby_adf1_ones_tens_down': '(>K:ADF_10_DEC)',
    'sim/radios/stby_adf1_ones_tens_up': '(>K:ADF_10_INC)',
    'sim/radios/com1_standy_flip': '(>K:COM_STBY_RADIO_SWAP)',
    'sim/radios/com2_standy_flip': '(>K:COM2_RADIO_SWAP)',
    'sim/radios/nav1_standy_flip': '(>K:NAV1_RADIO_SWAP)',
    'sim/radios/nav2_standy_flip': '(>K:NAV2_RADIO_SWAP)',
    'sim/radios/adf1_standy_flip': '(>K:ADF1_RADIO_SWAP)',
    'sim/transponder/transponder_thousands_down': '(>K:XPNDR_1000_DEC)',
    'sim/transponder/transponder_thousands_up': '(>K:XPNDR_1000_INC)',
    'sim/transponder/transponder_hundreds_down': '(>K:XPNDR_100_DEC)',
    'sim/transponder/transponder_hundreds_up': '(>K:XPNDR_100_INC)',
    'sim/transponder/transponder_tens_down': '(>K:XPNDR_10_DEC)',
    'sim/transponder/transponder_tens_up': '(>K:XPNDR_10_INC)',
    'sim/transponder/transponder_ones_down': '(>K:XPNDR_1_DEC)',
    'sim/transponder/transponder_ones_up': '(>K:XPNDR_1_INC)',
    # lights
    'sim/lights/nav_lights_on': '1 (>K:NAV_LIGHTS_SET)',
    'sim/lights/nav_lights_off': '0 (>K:NAV_LIGHTS_SET)',
    'sim/lights/strobe_lights_on': '1 (>K:STROBES_SET)',
    'sim/lights/strobe_lights_off': '0 (>K:STROBES_SET)',
    'sim/lights/beacon_lights_on': '1 (>K:BEACON_LIGHTS_SET)',
    'sim/lights/beacon_lights_off': '0 (>K:BEACON_LIGHTS_SET)',
    'sim/lights/taxi_lights_on': '1 (>K:TAXI_LIGHTS_SET)',
    'sim/lights/taxi_lights_off': '0 (>K:TAXI_LIGHTS_SET)',
    'sim/lights/landing_01_light_on': '1 (>K:LANDING_LIGHTS_SET)',
    'sim/lights/landing_01_light_off': '0 (>K:LANDING_LIGHTS_SET)',
    'sim/lights/landing_02_light_on': None,   # same switch as landing light 1 in MSFS
    'sim/lights/landing_02_light_off': None,
    'sim/annunciator/test_all_annunciators': None,
    # ice
    'sim/ice/pitot_heat1_on': '1 (>K:PITOT_HEAT_SET)',
    'sim/ice/pitot_heat1_off': '0 (>K:PITOT_HEAT_SET)',
    'sim/ice/pitot_heat0_on': None,           # PITOT_HEAT_SET already covers all probes
    'sim/ice/pitot_heat0_off': None,
    'sim/ice/inlet_heat0_on': '1 (>K:ANTI_ICE_SET)',
    'sim/ice/inlet_heat0_off': '0 (>K:ANTI_ICE_SET)',
    'sim/ice/inlet_heat1_on': None,           # ANTI_ICE_SET covers all engines
    'sim/ice/inlet_heat1_off': None,
    'sim/ice/wing_heat_on': toggle_to('(A:STRUCTURAL DEICE SWITCH,bool)', 'TOGGLE_STRUCTURAL_DEICE', True),
    'sim/ice/wing_heat_off': toggle_to('(A:STRUCTURAL DEICE SWITCH,bool)', 'TOGGLE_STRUCTURAL_DEICE', False),
    # fuel / electrical
    'sim/fuel/fuel_pump_1_on': toggle_to('(A:GENERAL ENG FUEL PUMP SWITCH:1,bool)', 'TOGGLE_ELECT_FUEL_PUMP1', True),
    'sim/fuel/fuel_pump_1_off': toggle_to('(A:GENERAL ENG FUEL PUMP SWITCH:1,bool)', 'TOGGLE_ELECT_FUEL_PUMP1', False),
    'sim/fuel/fuel_pump_2_on': toggle_to('(A:GENERAL ENG FUEL PUMP SWITCH:2,bool)', 'TOGGLE_ELECT_FUEL_PUMP2', True),
    'sim/fuel/fuel_pump_2_off': toggle_to('(A:GENERAL ENG FUEL PUMP SWITCH:2,bool)', 'TOGGLE_ELECT_FUEL_PUMP2', False),
    'sim/systems/avionics_on': '1 (>K:AVIONICS_MASTER_SET)',
    'sim/systems/avionics_off': '0 (>K:AVIONICS_MASTER_SET)',
    'sim/electrical/cross_tie_on': None,
    'sim/electrical/cross_tie_off': None,
    'sim/electrical/battery_1_on': '(>K:MASTER_BATTERY_ON)',
    'sim/electrical/battery_1_off': '(>K:MASTER_BATTERY_OFF)',
    'sim/electrical/generator_1_on': '(>K:ALTERNATOR_ON)',
    'sim/electrical/generator_1_off': '(>K:ALTERNATOR_OFF)',
    'sim/electrical/generator_2_on': None,    # ALTERNATOR_ON/OFF switch all alternators
    'sim/electrical/generator_2_off': None,
    # magnetos
    'sim/magnetos/magnetos_off': '(>K:MAGNETO_OFF)',
    'sim/magnetos/magnetos_left_1': '(>K:MAGNETO_LEFT)',
    'sim/magnetos/magnetos_right_1': '(>K:MAGNETO_RIGHT)',
    'sim/magnetos/magnetos_both': '(>K:MAGNETO_BOTH)',
    'sim/starters/engage_starter_1': '(>K:MAGNETO_START) 1 (>K:SET_STARTER1_HELD)',
    # autopilot
    'sim/autopilot/servos_toggle': '(>K:AP_MASTER)',
    'sim/autopilot/heading': '(>K:AP_PANEL_HEADING_HOLD)',
    'sim/autopilot/NAV': '(>K:AP_NAV1_HOLD)',
    'sim/autopilot/altitude_hold': '(>K:AP_ALT_HOLD)',
    'sim/autopilot/vertical_speed': '(>K:AP_VS_HOLD)',
    'sim/autopilot/approach': '(>K:AP_APR_HOLD)',
    'sim/autopilot/back_course': '(>K:AP_BC_HOLD)',
    'sim/autopilot/level_change': '(>K:FLIGHT_LEVEL_CHANGE)',
    'laminar/B738/autopilot/speed_press': '(>K:AP_PANEL_SPEED_HOLD)',
    'sim/autopilot/autothrottle_on': toggle_to('(A:AUTOPILOT THROTTLE ARM,bool)', 'AUTO_THROTTLE_ARM', True),
    'sim/autopilot/autothrottle_off': toggle_to('(A:AUTOPILOT THROTTLE ARM,bool)', 'AUTO_THROTTLE_ARM', False),
    'sim/autopilot/airspeed_down': '(>K:AP_SPD_VAR_DEC)',
    'sim/autopilot/airspeed_up': '(>K:AP_SPD_VAR_INC)',
    'sim/autopilot/heading_down': '(>K:HEADING_BUG_DEC)',
    'sim/autopilot/heading_up': '(>K:HEADING_BUG_INC)',
    'sim/autopilot/vertical_speed_down': '(>K:AP_VS_VAR_DEC)',
    'sim/autopilot/vertical_speed_up': '(>K:AP_VS_VAR_INC)',
    'sim/autopilot/altitude_down': '(>K:AP_ALT_VAR_DEC)',
    'sim/autopilot/altitude_up': '(>K:AP_ALT_VAR_INC)',
    'sim/radios/obs1_down': '(>K:VOR1_OBI_DEC)',
    'sim/radios/obs1_up': '(>K:VOR1_OBI_INC)',
    'sim/radios/copilot_obs_HSI_down': None,  # CRS already moves VOR1 OBS
    'sim/radios/copilot_obs_HSI_up': None,
}

# X-Plane dataref writes used as inputs: (path, value) -> MSFS RPN code
DATAREF_INPUTS = {
    ('mobiflight/starter', '15'): '(>K:MAGNETO_START) 1 (>K:SET_STARTER1_HELD) 1 (>K:SET_STARTER2_HELD)',
    ('mobiflight/starter', '0'): '0 (>K:SET_STARTER1_HELD) 0 (>K:SET_STARTER2_HELD)',
    ('sim/cockpit2/switches/instrument_brightness_ratio[0]', '1'): '1 (>K:PANEL_LIGHTS_SET)',
    ('sim/cockpit2/switches/instrument_brightness_ratio[0]', '0'): '0 (>K:PANEL_LIGHTS_SET)',
}

ACTION = re.compile(r'<(on\w+) type="XplaneInputAction" inputType="(\w+)" path="([^"]*)" expression="([^"]*)" />')
SOURCE = re.compile(r'<source type="XplaneDataRef" path="([^"]*)" />')
EMPTY_LVAR = '<source type="SimConnect" VarType="LVAR" Value="" />'


def convert(text):
    missing = set()

    def config(block):
        unmapped = False

        def action(m):
            nonlocal unmapped
            tag, kind, path, expr = m.groups()
            key = path if kind == 'Command' else (path, expr)
            table = COMMANDS if kind == 'Command' else DATAREF_INPUTS
            if key not in table:
                missing.add(key)
            code = table.get(key)
            if code is None:
                unmapped = True
                return f'<{tag} />'
            return f'<{tag} type="MSFS2020CustomInputAction" command="{escape(code)}" />'

        def source(m):
            nonlocal unmapped
            path = m.group(1)
            if path not in OUTPUTS:
                missing.add(path)
                unmapped = True
                return '<source type="SimConnect" VarType="CODE" Value="0" />'
            return f'<source type="SimConnect" VarType="CODE" Value="{escape(OUTPUTS[path])}" />'

        block = ACTION.sub(action, block)
        block = SOURCE.sub(source, block)
        # constant "brightness" configs read an empty LVAR, which is 0 when connected to X-Plane
        block = block.replace(EMPTY_LVAR, '<source type="SimConnect" VarType="CODE" Value="0" />')
        is_output = 'OutputConfigItem' in block
        if (is_output and unmapped) or (not is_output and unmapped and 'MSFS2020CustomInputAction' not in block):
            block = block.replace('<active>true</active>', '<active>false</active>', 1)
        return block

    text = re.sub(r'    <config guid="[^"]+">.*?</config>', lambda m: config(m.group(0)), text, flags=re.S)
    return text, missing


if __name__ == '__main__':
    src, dst = sys.argv[1], sys.argv[2]
    text = open(src, encoding='utf-8', newline='').read()
    out, missing = convert(text)
    for key in sorted(map(str, missing)):
        print('not mapped (config deactivated):', key)
    open(dst, 'w', encoding='utf-8', newline='').write(out)
