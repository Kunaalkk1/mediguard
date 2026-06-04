import random
from grove_base import ON_PI, grovepi

LIGHT_PORT = 0        # analog A0      
GAS_PORT   = 2        # analog A2 MQ135,use the AO pin
PIR_PORT   = 2        # digital D2  
SOS_PORT   = 3        # digital D3 
PRESSURE_PORT = 1     # analog A1 RP-S40-ST         
PRESSURE_THRESHOLD = 400   # raw value above this = someone on the bed  # TUNE ON PI

def read_light():

    if ON_PI:
        return grovepi.analogRead(LIGHT_PORT)   # CONFIRM ON PI
    else:
        return random.randint(200, 800)
    
def read_gas():
    
    if ON_PI:
        return grovepi.analogRead(GAS_PORT)          # CONFIRM ON PI
    else:
        return random.randint(50, 600)
    
def read_motion():
    
    if ON_PI:
        return grovepi.digitalRead(PIR_PORT) == 1    # CONFIRM ON PI
    else:
        return random.choice([True, False])          # fake: random motion

def read_sos():
    
    if ON_PI:
        return grovepi.digitalRead(SOS_PORT) == 1    # CONFIRM ON PI
    else:
        return random.choice([False, False, False, True])  # fake: rarely pressed
    
def read_pressure():
    """Returns True if someone is on the bed, False if the bed is empty"""
    if ON_PI:
        raw = grovepi.analogRead(PRESSURE_PORT)   # CONFIRM ON PI
    else:
        raw = random.randint(200,650)
    on_bed = raw > PRESSURE_THRESHOLD
    return (raw, on_bed)
    

if __name__ == "__main__":
    print("Testing Grove sensor drivers...\n")
    print(f"  light  = {read_light()}")
    print(f"  gas    = {read_gas()}")
    print(f"  motion = {read_motion()}")
    p_raw, p_on_bed = read_pressure()
    print(f"  pressure = {p_raw}  (on bed: {p_on_bed})")