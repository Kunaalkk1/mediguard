(define (problem room101-current-cycle)
  (:domain smart-hospital-room)

  (:objects
    room101 - room
    patient1 - patient
    light1 - light
    fan1 - fan
    door1 - door
    buzzer1 - buzzer
    redled1 - red-led
  )

  (:init
    (light-in light1 room101)
    (fan-in fan1 room101)
    (door-in door1 room101)
    (buzzer-in buzzer1 room101)
    (red-led-in redled1 room101)
    (patient-in patient1 room101)
    (light-on light1)
    (light-dim light1)
    (fan-on fan1)
    (fan-medium fan1)
    (fan-not-high fan1)
    (door-locked door1)
    (buzzer-not-on buzzer1)
    (buzzer-not-high buzzer1)
    (red-led-not-on redled1)
    (red-led-not-blinking redled1)
    (room-normal room101)
    (patient-awake patient1)
    (sos-not-pressed room101)
    (air-not-hazardous room101)
    (temperature-not-unsafe room101)
    (temperature-not-hot room101)
    (humidity-not-high room101)
    (room-not-dark room101)
    (patient-on-bed patient1)
    (motion-recent patient1)
    (spo2-not-low patient1)
    (pulse-not-abnormal patient1)
    (out-of-bed-alert-not-due patient1)
  )

  (:goal
    (and
              (light-on light1)
              (light-dim light1)
              (fan-on fan1)
              (fan-medium fan1)
              (fan-not-high fan1)
              (door-locked door1)
              (buzzer-not-on buzzer1)
              (buzzer-not-high buzzer1)
              (red-led-not-on redled1)
              (red-led-not-blinking redled1)
            )
  )
)
