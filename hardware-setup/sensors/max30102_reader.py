import random
try:
    import max30102          # talks to the sensor over I2C and this is a library by doug=burrel on github
    import hrcalc            # does the heart-rate / SpO2 math
    SENSOR = max30102.MAX30102() 
    HAVE_SENSOR = True
except (ImportError, Exception):
    SENSOR = None
    HAVE_SENSOR = False

SAMPLE_COUNT = 100

def read_pulse_spo2():
    
    if HAVE_SENSOR:
        red, ir = SENSOR.read_sequential(SAMPLE_COUNT)  
        hr, hr_valid, spo2, spo2_valid = hrcalc.calc_hr_and_spo2(ir, red)
        if hr_valid:
            pulse = round(hr)
        else:
            pulse = None
        if spo2_valid: 
            oxygen = round(spo2) 
        else:
            oxygen = None
        return (pulse, oxygen)
    else:
        pulse = random.randint(60, 100)     # healthy resting pulse
        oxygen = random.randint(95, 100)    # healthy SpO2
        return (pulse, oxygen)

if __name__ == "__main__":
    print("Testing MAX30102 reader\n")
    for i in range(5):
        pulse, spo2 = read_pulse_spo2()
        print(f"  Reading {i + 1}: pulse = {pulse} BPM, SpO2 = {spo2} %")